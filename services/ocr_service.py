"""
OCR service for extracting text from logbook images using Tesseract.

Provides image preprocessing and text extraction capabilities optimized
for pilot logbook pages (ASA/Jeppesen format).
"""

from __future__ import annotations

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

try:
    from google.cloud import vision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    print("Warning: Google Cloud Vision not installed")
    print("Install with: pip install google-cloud-vision")


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

    def extract_text_with_google_vision(self, image_path: str, structured: bool = False) -> str:
        """
        Extract text using Google Cloud Vision API (supports handwriting).

        This method uses Google's machine learning models which are much better
        at recognizing handwritten text than Tesseract.

        Args:
            image_path: Path to input image
            structured: If True, return structured data with word positions

        Returns:
            Extracted text as string, or structured data if requested
        """
        if not VISION_AVAILABLE:
            print("ERROR: Google Cloud Vision not available, falling back to Tesseract")
            return self.extract_text_from_image(image_path)

        try:
            # Check for credentials
            import os as os_module
            creds_path = os_module.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'Not set')
            print(f"GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
            if creds_path != 'Not set' and os_module.path.exists(creds_path):
                print(f"Credentials file exists: {creds_path}")
            else:
                print(f"WARNING: Credentials file not found or env var not set")

            print(f"Initializing Google Vision API client for: {image_path}")
            # Initialize Vision API client
            client = vision.ImageAnnotatorClient()
            print("Vision API client initialized successfully")

            # Load image
            with open(image_path, 'rb') as image_file:
                content = image_file.read()

            print(f"Image loaded: {len(content)} bytes")
            image = vision.Image(content=content)

            # Perform document text detection (best for dense text like logbooks)
            print("Calling Vision API document_text_detection...")
            response = client.document_text_detection(image=image)
            print("Vision API call completed")

            if response.error.message:
                raise Exception(f"Vision API error: {response.error.message}")

            if structured and response.full_text_annotation:
                # Return structured data with word positions for table parsing
                return self._extract_structured_data(response.full_text_annotation)

            # Extract full text
            text = response.full_text_annotation.text if response.full_text_annotation else ""

            return text.strip()

        except Exception as e:
            print(f"Error with Google Vision API: {e}")
            print("Falling back to Tesseract OCR")
            return self.extract_text_from_image(image_path)

    def _extract_structured_data(self, annotation) -> dict:
        """
        Extract structured data with word positions from Vision API response.

        This helps parse tabular data by understanding spatial layout.
        """
        rows = {}  # Group words by row (y-coordinate)

        for page in annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        # Get word text
                        word_text = ''.join([symbol.text for symbol in word.symbols])

                        # Get bounding box to determine position
                        vertices = word.bounding_box.vertices
                        y_pos = vertices[0].y  # Top y-coordinate

                        # Group words by row (within 10 pixels tolerance)
                        row_key = y_pos // 10 * 10
                        if row_key not in rows:
                            rows[row_key] = []

                        rows[row_key].append({
                            'text': word_text,
                            'x': vertices[0].x,
                            'y': y_pos
                        })

        # Sort rows by y-position and words within each row by x-position
        sorted_rows = []
        for y in sorted(rows.keys()):
            words = sorted(rows[y], key=lambda w: w['x'])
            row_text = ' '.join([w['text'] for w in words])
            sorted_rows.append(row_text)

        return '\n'.join(sorted_rows)
