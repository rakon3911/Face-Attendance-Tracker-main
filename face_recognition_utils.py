import cv2
import numpy as np
from models import Employee
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_face_encoding(image):
    """
    Extract face encoding from an image

    Args:
        image: Image as numpy array

    Returns:
        Numpy array of face encoding or None if no face detected
    """
    try:
        # Convert to grayscale for face detection
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Load the face detector
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # Detect faces
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

        if len(faces) == 0:
            logger.warning("No face detected in the image")
            return None

        # Use the first face detected (largest one if multiple)
        x, y, w, h = faces[0]

        # Extract face region
        face_img = image[y:y+h, x:x+w]

        # Resize to a standard size - using 128x128 for consistency
        face_img = cv2.resize(face_img, (128, 128))
        
        # Convert to grayscale to reduce dimensionality and improve compatibility
        face_gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        
        # Flatten the image as a simple face encoding
        encoding = face_gray.flatten()
        
        # Normalize the encoding for better comparison
        if np.any(encoding):  # Avoid division by zero
            encoding = encoding / np.linalg.norm(encoding)

        return encoding

    except Exception as e:
        logger.error(f"Error in get_face_encoding: {e}")
        return None

def identify_employee(face_encoding, department_id):
    """
    Identify an employee based on face encoding

    Args:
        face_encoding: Numpy array of face encoding
        department_id: ID of the department to search for employees

    Returns:
        Tuple of (employee_id, employee_name, confidence_percentage) or (None, None, 0) if not identified
    """
    try:
        from app import db

        # Get all employees in the department
        employees = Employee.query.filter_by(department_id=department_id).all()

        if not employees:
            logger.warning(f"No employees found in department {department_id}")
            return None, None, 0

        # Find the best match
        best_match = None
        best_similarity = -1

        for employee in employees:
            if employee.face_encoding is None:
                continue
                
            # Ensure the encodings are of the same shape before comparison
            if face_encoding.shape != employee.face_encoding.shape:
                logger.warning(f"Encoding shape mismatch: {face_encoding.shape} vs {employee.face_encoding.shape}")
                
                # Try to resize the encodings to match
                try:
                    # If current encoding is larger, resize it to match employee encoding
                    if face_encoding.size > employee.face_encoding.size:
                        # Determine the square root of the size to get dimensions
                        dim = int(np.sqrt(employee.face_encoding.size))
                        # Reshape to 2D, resize, and flatten again
                        img_size = int(np.sqrt(face_encoding.size))
                        img_2d = face_encoding.reshape(img_size, img_size)
                        img_resized = cv2.resize(img_2d, (dim, dim))
                        face_encoding = img_resized.flatten()
                    else:
                        # Skip this employee if we can't resize correctly
                        continue
                except Exception as resize_err:
                    logger.error(f"Error resizing encoding: {resize_err}")
                    continue

            # Calculate similarity (using Euclidean distance)
            try:
                # Calculer la distance euclidienne normalisée
                distance = np.linalg.norm(face_encoding - employee.face_encoding)
                # Convertir la distance en similarité (plus la distance est faible, plus la similarité est élevée)
                # La formule est ajustée pour être plus stricte
                similarity = 1.0 / (1.0 + distance * 2)  # Facteur multiplicatif pour réduire la similarité
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = employee
            except Exception as compare_err:
                logger.error(f"Error comparing encodings: {compare_err}")
                continue

        # Seuil de confiance augmenté à 0.85 pour plus de précision
        confidence_threshold = 0.65
        
        if best_similarity > confidence_threshold and best_match:
            # Convert similarity to percentage (0-100)
            confidence_percentage = int(min(best_similarity * 100, 100))
            logger.info(f"Employee identified: {best_match.full_name} with confidence {confidence_percentage}%")
            return best_match.id, best_match.full_name, confidence_percentage
        else:
            logger.warning(f"No employee matched with sufficient confidence (best: {best_similarity:.2f})")
            return None, None, 0

    except Exception as e:
        logger.error(f"Error in identify_employee: {e}")
        return None, None, 0

def process_frame(frame):
    """
    Process a video frame for facial recognition

    Args:
        frame: Video frame as numpy array

    Returns:
        Processed frame with annotations
    """
    try:
        # Make a copy to avoid modifying original
        display_frame = frame.copy()

        # Convert to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Load the face detector with less sensitivity
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # Detect faces with very low sensitivity (increased scaleFactor and minNeighbors)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=10, minSize=(60, 60))

        # Draw rectangles around faces with more information
        for (x, y, w, h) in faces:
            # Dessiner un rectangle vert autour du visage
            cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

            # Ajouter une zone de texte en haut du rectangle
            cv2.rectangle(display_frame, (x, y-30), (x+w, y), (0, 255, 0), -1)
            cv2.putText(display_frame, "Visage détecté", (x+5, y-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        return display_frame

    except Exception as e:
        logger.error(f"Error in process_frame: {e}")
        return frame