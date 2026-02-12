"""
OCR service for extracting text from logbook images using Tesseract.

Provides image preprocessing and text extraction capabilities optimized
for pilot logbook pages (ASA/Jeppesen format).
"""

import os
from typing import Optional

try:
    import cv2
    import numpy as np
    import pytesseract
    from PIL import Image
except ImportError as e:
    print(f"Warning: OCR dependencies not installed: {e}")
    print("Install with: pip install pytesseract pillow opencv-python")


class LogbookOCRService:
    """Service for OCR extraction from logbook images."""

    def __init__(self):
        """Initialize OCR service."""
        # Check if Tesseract is installed
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            print("Warning: Tesseract OCR not found on system")
            print("Install with:")
            print("  Ubuntu/Debian: sudo apt-get install tesseract-ocr")
            print("  macOS: brew install tesseract")
            print("  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki")

    def preprocess_image(self, image_path: str) -> Optional[np.ndarray]:
        """
        Preprocess image for better OCR accuracy.

        Applies:
        - Grayscale conversion
        - Denoising
        - Adaptive thresholding
        - Deskewing

        Args:
            image_path: Path to input image

        Returns:
            Preprocessed image as numpy array, or None on error
        """
        try:
            # Load image
            img = cv2.imread(image_path)
            if img is None:
                print(f"Error: Could not load image from {image_path}")
                return None

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Denoise
            denoised = cv2.fastNlMeansDenoising(gray, h=10)

            # Adaptive thresholding for better contrast
            thresh = cv2.adaptiveThreshold(
                denoised,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,
                2
            )

            # Deskew (detect rotation and correct)
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) > 0:
                angle = cv2.minAreaRect(coords)[-1]

                # Correct angle (OpenCV quirk)
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle

                # Only deskew if rotation is significant (> 0.5 degrees)
                if abs(angle) > 0.5:
                    (h, w) = thresh.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    thresh = cv2.warpAffine(
                        thresh,
                        M,
                        (w, h),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_REPLICATE
                    )

            return thresh

        except Exception as e:
            print(f"Error preprocessing image: {e}")
            return None

    def extract_text_from_image(self, image_path: str, preprocess: bool = True) -> str:
        """
        Extract text from image using Tesseract OCR.

        Args:
            image_path: Path to input image
            preprocess: Whether to apply preprocessing (default True)

        Returns:
            Extracted text as string
        """
        try:
            if preprocess:
                # Use preprocessed image
                processed = self.preprocess_image(image_path)
                if processed is None:
                    # Fall back to raw image
                    img = Image.open(image_path)
                else:
                    img = Image.fromarray(processed)
            else:
                # Use raw image
                img = Image.open(image_path)

            # Tesseract configuration
            # PSM 6: Assume a single uniform block of text
            # oem 3: Use best available OCR engine mode
            config = '--psm 6 --oem 3'

            # Extract text
            text = pytesseract.image_to_string(img, config=config)

            return text.strip()

        except Exception as e:
            print(f"Error extracting text from image: {e}")
            return ""

    def extract_with_confidence(self, image_path: str) -> dict:
        """
        Extract text with confidence scores for each word.

        Useful for identifying low-confidence OCR results that may need review.

        Args:
            image_path: Path to input image

        Returns:
            Dict with 'text', 'confidence', and 'data' (detailed results)
        """
        try:
            processed = self.preprocess_image(image_path)
            if processed is None:
                img = Image.open(image_path)
            else:
                img = Image.fromarray(processed)

            # Get detailed data including confidence
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

            # Extract text and average confidence
            texts = [word for word in data['text'] if word.strip()]
            confidences = [
                conf for conf, word in zip(data['conf'], data['text'])
                if word.strip() and conf != -1
            ]

            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            return {
                'text': ' '.join(texts),
                'confidence': avg_confidence,
                'data': data
            }

        except Exception as e:
            print(f"Error extracting with confidence: {e}")
            return {'text': '', 'confidence': 0, 'data': {}}
