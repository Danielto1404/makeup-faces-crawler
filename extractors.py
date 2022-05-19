from typing import Tuple, List, Optional
from PIL.JpegImagePlugin import JpegImageFile
import numpy as np
from PIL import Image
import extcolors
import cv2
import dlib


class PaletteExtractor:
    def get_palette(self, img: JpegImageFile, proportionately: bool = False,
                    height: int = 300, width: int = 50) -> JpegImageFile:
        colors = self.get_colors(img)
        palette = self.create_color_palette(colors, proportionately, height, width)
        return Image.fromarray(palette)

    def get_colors(self, img: JpegImageFile) -> list:
        colors, _ = extcolors.extract_from_image(img)
        return colors

    def create_color_palette(self, colors: list, proportionately: bool = False,
                             height: int = 300, width: int = 50) -> np.ndarray:
        total_pixels = sum([pixels_count for color, pixels_count in colors])

        bar = np.zeros((height, width, 3), dtype="uint8")
        start_y = 0
        percent = 1 / len(colors)

        for color, pixels_count in colors:
            if proportionately:
                percent = pixels_count / total_pixels
            end_y = start_y + (percent * height)
            top_left_corner = (0, int(start_y))
            bottom_right_corner = (width, int(end_y))
            cv2.rectangle(bar, top_left_corner, bottom_right_corner, np.array(color).astype("uint8").tolist(), -1)
            start_y = end_y
        return bar


class MakeupExtractor:
    def __init__(self, use_cnn=False) -> None:
        # define landmarks numbers for different regions
        self.left_eyelid = [0] + list(range(17, 22)) + [27, 28]
        self.right_eyelid = [28, 27] + list(range(22, 27)) + [16]
        self.eyelids = [self.left_eyelid, self.right_eyelid]

        self.left_eye = list(range(36, 42))
        self.right_eye = list(range(42, 48))

        self.mouth = list(range(48, 60))
        self.teeth = list(range(60, 68))

        self.use_cnn = use_cnn
        if self.use_cnn:
            detector_weights_path = 'mmod_human_face_detector.dat'
            self.face_detector = dlib.cnn_face_detection_model_v1(detector_weights_path)
        else:
            self.face_detector = dlib.get_frontal_face_detector()
        predictor_weights_path = 'shape_predictor_68_face_landmarks.dat'
        self.landmarks_predictor = dlib.shape_predictor(predictor_weights_path)

    def get_landmarks(self, img: np.ndarray, face: dlib.rectangle, regions: list) -> list:
        points = []
        for region in regions:
            landmarks = self.landmarks_predictor(image=img, box=face)
            cur_points = []
            for n in region:
                x = landmarks.part(n).x
                y = landmarks.part(n).y
                cur_points.append(np.array([x, y]))
            points.append(np.array(cur_points))
        return points

    def get_mask(self, img: np.ndarray, points: list) -> np.ndarray:
        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        mask = cv2.fillPoly(mask, points, 255)
        return mask

    def add_transparent_background(self, img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        res = img.copy()
        res = cv2.cvtColor(res, cv2.COLOR_BGR2BGRA)
        res[:, :, 3] = mask[:, :, 0]
        return res

    def get_eye(self, img: np.ndarray,
                face: dlib.rectangle, part: int = 2) -> Tuple[np.ndarray, list]:
        # 0 is left eye, 1 is right, 2 is both
        if part == 0:
            regions = [self.left_eye]
        elif part == 1:
            regions = [self.right_eye]
        else:
            regions = [self.left_eye, self.right_eye]
        eyes_landmarks = self.get_landmarks(img, face, regions)
        eyes_mask = self.get_mask(img, eyes_landmarks)
        return eyes_mask, eyes_landmarks

    def get_eyelid(self, img: np.ndarray,
                   face: dlib.rectangle, part: int = 2) -> Tuple[np.ndarray, list]:
        # 0 is left eyelid, 1 is right, 2 is both
        if part == 0:
            regions = [self.left_eyelid]
        elif part == 1:
            regions = [self.right_eyelid]
        else:
            regions = [self.left_eyelid, self.right_eyelid]
        eyelids_landmarks = self.get_landmarks(img, face, regions)
        eyelids_mask = self.get_mask(img, eyelids_landmarks)
        return eyelids_mask, eyelids_landmarks

    def get_teeth(self, img: np.ndarray, face: dlib.rectangle) -> Tuple[np.ndarray, list]:
        teeth_landmarks = self.get_landmarks(img, face, [self.teeth])
        teeth_mask = self.get_mask(img, teeth_landmarks)
        return teeth_mask, teeth_landmarks

    def get_mouth(self, img: np.ndarray, face: dlib.rectangle) -> Tuple[np.ndarray, list]:
        mouth_landmarks = self.get_landmarks(img, face, [self.mouth])
        mouth_mask = self.get_mask(img, mouth_landmarks)
        return mouth_mask, mouth_landmarks

    def get_crop_coordinates(self, landmarks: list) -> Tuple[int, int, int, int]:
        top = np.min([y for coordinate in landmarks for x, y in coordinate])
        bottom = np.max([y for coordinate in landmarks for x, y in coordinate])
        left = np.min([x for coordinate in landmarks for x, y in coordinate])
        right = np.max([x for coordinate in landmarks for x, y in coordinate])
        return top, right, bottom, left

    def get_image_from_mask(self, img: np.ndarray, mask: np.ndarray, landmarks: list) -> JpegImageFile:
        mask = np.array([mask] * 3)
        mask = np.transpose(mask, [1, 2, 0])
        img_mask = cv2.bitwise_and(img, mask)
        top, right, bottom, left = self.get_crop_coordinates(landmarks)
        img_crop = img_mask[top:bottom, left:right]
        mask_crop = mask[top:bottom, left:right]
        transparent_img = Image.fromarray(self.add_transparent_background(img_crop, mask_crop))
        return transparent_img

    def get_face(self, img: np.ndarray) -> Optional[dlib.rectangle]:
        faces = self.face_detector(img)
        if not faces:
            return None
        if self.use_cnn:
            face = faces[0].rect
        else:
            face = faces[0]
        return face

    def extract(self, img: JpegImageFile) -> Optional[List[JpegImageFile]]:
        img = np.array(img)

        # face boundary box
        face = self.get_face(img)
        if not face:
            return None

        # left eye
        left_eye_mask, left_eye_landmarks = self.get_eye(img, face, 0)
        left_eye = self.get_image_from_mask(img, left_eye_mask, left_eye_landmarks)

        # right eye
        right_eye_mask, right_eye_landmarks = self.get_eye(img, face, 1)
        right_eye = self.get_image_from_mask(img, right_eye_mask, right_eye_landmarks)

        # left and right eyes
        left_right_eyes_mask, left_right_eyes_landmarks = self.get_eye(img, face, 2)
        left_right_eyes = self.get_image_from_mask(img, left_right_eyes_mask, left_right_eyes_landmarks)

        # left eyelid
        left_eyelid_mask, left_eyelid_landmarks = self.get_eyelid(img, face, 0)
        left_eyelid_mask = cv2.bitwise_and(left_eyelid_mask, (255 - left_eye_mask))
        left_eyelid = self.get_image_from_mask(img, left_eyelid_mask, left_eyelid_landmarks)

        # right eyelid
        right_eyelid_mask, right_eyelid_landmarks = self.get_eyelid(img, face, 1)
        right_eyelid_mask = cv2.bitwise_and(right_eyelid_mask, (255 - right_eye_mask))
        right_eyelid = self.get_image_from_mask(img, right_eyelid_mask, right_eyelid_landmarks)

        # left and right eyelids
        left_right_eyelids_mask, left_right_eyelids_landmarks = self.get_eyelid(img, face, 2)
        left_right_eyelids_mask = cv2.bitwise_and(left_right_eyelids_mask, (255 - left_right_eyes_mask))
        left_right_eyelids = self.get_image_from_mask(img, left_right_eyelids_mask, left_right_eyelids_landmarks)

        # teeth
        teeth_mask, teeth_landmarks = self.get_teeth(img, face)
        teeth = self.get_image_from_mask(img, teeth_mask, teeth_landmarks)

        # mouth
        mouth_mask, mouth_landmarks = self.get_mouth(img, face)
        mouth = self.get_image_from_mask(img, mouth_mask, mouth_landmarks)

        # lips
        lips_mask = cv2.bitwise_and(mouth_mask, (255 - teeth_mask))
        lips = self.get_image_from_mask(img, lips_mask, mouth_landmarks)

        # eyelids and lips
        eyelids_lips_mask = cv2.bitwise_or(left_right_eyelids_mask, lips_mask)
        eyelids_lips = self.get_image_from_mask(img, eyelids_lips_mask, left_right_eyelids_landmarks + mouth_landmarks)

        return [left_eye, right_eye, left_right_eyes, left_eyelid, right_eyelid, left_right_eyelids,
                teeth, mouth, lips, eyelids_lips]


def extractor(img: JpegImageFile) -> Optional[list]:
    makeup_extractor = MakeupExtractor()
    try:
        images = makeup_extractor.extract(img)
        if images is not None:
            palette_extractor = PaletteExtractor()
            palette_img = palette_extractor.get_palette(img)
            return images + [palette_img]
    except Exception:
        return None
