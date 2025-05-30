document.addEventListener('DOMContentLoaded', function() {
    // DOM elements
    const startCameraButton = document.getElementById('startCamera');
    const webcamElement = document.getElementById('webcam');
    const canvasElement = document.getElementById('canvas');
    const recognitionStatus = document.getElementById('recognitionStatus');
    const classIdElement = document.getElementById('classId');
    const confidenceDisplay = document.getElementById('confidenceDisplay');
    const confidenceValue = document.getElementById('confidenceValue');
    const scheduleSelect = document.getElementById('scheduleSelect');
    const scheduleWarning = document.getElementById('scheduleWarning');
    const faceFrame = document.getElementById('face-frame');

    // Variables for camera handling
    let stream = null;
    let captureInterval = null;
    let streaming = false;
    const width = 640;
    let height = 0;

    // Function to start the camera
    function startCamera() {
        // Check if a schedule is selected
        if (scheduleSelect && scheduleSelect.value === "") {
            scheduleWarning.style.display = 'block';
            return;
        } else if (scheduleWarning) {
            scheduleWarning.style.display = 'none';
        }

        // If camera is already running, stop it
        if (streaming) {
            stopCamera();
            startCameraButton.innerHTML = '<i class="fas fa-camera"></i> Démarrer la caméra';
            if (faceFrame) faceFrame.style.display = 'none';
            recognitionStatus.style.display = 'none';
            confidenceDisplay.style.display = 'none';
            return;
        }

        // Start the camera
        recognitionStatus.style.display = 'block';
        recognitionStatus.innerText = 'Démarrage de la caméra...';

        navigator.mediaDevices.getUserMedia({ 
            video: true,
            audio: false
        })
        .then(function(videoStream) {
            stream = videoStream;
            webcamElement.srcObject = stream;
            webcamElement.play();
            streaming = true;

            startCameraButton.innerHTML = '<i class="fas fa-stop"></i> Arrêter la caméra';
            startCameraButton.disabled = false;

            if (faceFrame) faceFrame.style.display = 'block';

            recognitionStatus.innerText = 'Caméra active. Positionnez votre visage pour la reconnaissance.';
            recognitionStatus.classList.remove('alert-danger');
            recognitionStatus.classList.add('alert-info');

            // Adjust canvas dimensions once the video is loaded
            webcamElement.addEventListener('canplay', function() {
                if (!streaming) {
                    height = webcamElement.videoHeight / (webcamElement.videoWidth / width);
                    webcamElement.setAttribute('width', width);
                    webcamElement.setAttribute('height', height);
                    canvasElement.setAttribute('width', width);
                    canvasElement.setAttribute('height', height);
                    streaming = true;
                }
            });

            // Start capturing frames for face recognition
            captureInterval = setInterval(captureFrame, 3000);
        })
        .catch(function(error) {
            console.error('Erreur d\'accès à la caméra:', error);
            recognitionStatus.innerText = 'Erreur: Impossible d\'accéder à la caméra. ' + error.message;
            recognitionStatus.classList.remove('alert-info');
            recognitionStatus.classList.add('alert-danger');
            recognitionStatus.style.display = 'block';
        });
    }

    // Function to stop the camera
    function stopCamera() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            webcamElement.srcObject = null;
            stream = null;
        }
        
        if (captureInterval) {
            clearInterval(captureInterval);
            captureInterval = null;
        }
        
        streaming = false;
    }

    // Function to capture a frame and send for recognition
    function captureFrame() {
        if (!streaming || !stream) return;

        const context = canvasElement.getContext('2d');
        canvasElement.width = webcamElement.videoWidth;
        canvasElement.height = webcamElement.videoHeight;

        // Draw the current frame to the canvas
        context.drawImage(webcamElement, 0, 0, canvasElement.width, canvasElement.height);

        // Convert the canvas to base64 image
        const imageData = canvasElement.toDataURL('image/jpeg');

        // Send the image for processing
        processImage(imageData);
    }

    // Function to send the image for face recognition
    function processImage(imageData) {
        recognitionStatus.innerText = 'Analyse du visage en cours...';
        recognitionStatus.classList.remove('alert-danger', 'alert-success');
        recognitionStatus.classList.add('alert-info');

        // Make sure classIdElement exists before accessing its value
        const classId = classIdElement ? classIdElement.value : null;
        const scheduleId = scheduleSelect ? scheduleSelect.value : null;

        if (!classId) {
            console.error("L'élément d'ID de classe est manquant");
            recognitionStatus.innerText = "Erreur: ID de classe manquant";
            recognitionStatus.classList.remove('alert-info');
            recognitionStatus.classList.add('alert-danger');
            return;
        }

        if (!scheduleId) {
            scheduleWarning.style.display = 'block';
            stopCamera();
            startCameraButton.innerHTML = '<i class="fas fa-camera"></i> Démarrer la caméra';
            return;
        }

        const formData = new FormData();
        formData.append('class_id', classId);
        formData.append('schedule_id', scheduleId);
        formData.append('image', imageData);

        fetch('/process_attendance', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Successful recognition
                recognitionStatus.innerHTML = `
                    <div class="alert-heading h5">Étudiant reconnu!</div>
                    <div><strong>Nom:</strong> ${data.student_name}</div>
                    <div><strong>Compatibilité:</strong> ${data.confidence || 'N/A'}%</div>
                    <div class="mt-2 text-success">${data.message}</div>
                `;
                recognitionStatus.classList.remove('alert-info', 'alert-danger');
                recognitionStatus.classList.add('alert-success');

                // Display confidence
                if (data.confidence) {
                    confidenceValue.innerText = data.confidence;
                    confidenceDisplay.style.display = 'block';
                }

                // Create a flash effect
                createFlashEffect();

                // Add visual indication on student list
                highlightStudent(data.student_id);
            } else {
                // Recognition failed
                recognitionStatus.innerText = data.message || 'Reconnaissance faciale échouée';
                recognitionStatus.classList.remove('alert-info', 'alert-success');
                recognitionStatus.classList.add('alert-danger');
                confidenceDisplay.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Erreur lors de la reconnaissance faciale:', error);
            recognitionStatus.innerText = 'Erreur de connexion au serveur: ' + error.message;
            recognitionStatus.classList.remove('alert-info', 'alert-success');
            recognitionStatus.classList.add('alert-danger');
            confidenceDisplay.style.display = 'none';
        });
    }

    // Create a flash effect when a face is recognized
    function createFlashEffect() {
        const flashElement = document.createElement('div');
        flashElement.className = 'recognition-flash';
        document.body.appendChild(flashElement);

        // Remove the flash element after animation completes
        setTimeout(() => {
            document.body.removeChild(flashElement);
        }, 500);
    }

    // Highlight student in the list
    function highlightStudent(studentId) {
        const studentElement = document.getElementById(`student-${studentId}`);
        if (studentElement) {
            studentElement.classList.add('bg-success', 'text-white');

            const statusElement = studentElement.querySelector('.attendance-status');
            if (statusElement) {
                statusElement.style.display = 'block';
                const badge = statusElement.querySelector('.badge');
                if (badge) {
                    badge.textContent = 'Présent (reconnaissance faciale)';
                    badge.className = 'badge bg-success';
                }
            }

            // Remove highlighting after a few seconds
            setTimeout(() => {
                studentElement.classList.remove('bg-success', 'text-white');
            }, 5000);
        }
    }

    // Get CSRF token from meta tag
    function getCSRFToken() {
        const tokenElement = document.querySelector('meta[name="csrf-token"]');
        return tokenElement ? tokenElement.getAttribute('content') : '';
    }

    // Function for manual attendance marking
    window.markAttendance = function(studentId, present) {
        const classId = classIdElement ? classIdElement.value : '';
        const scheduleId = scheduleSelect ? scheduleSelect.value : '';
        
        // Verify that a session is selected
        if (scheduleSelect && !scheduleId) {
            if (scheduleWarning) scheduleWarning.style.display = 'block';
            return;
        }
        
        fetch('/mark_session_attendance', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': getCSRFToken()
            },
            body: new URLSearchParams({
                'student_id': studentId,
                'class_id': classId,
                'present': present,
                'schedule_id': scheduleId
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const studentElement = document.getElementById(`student-${studentId}`);
                const statusElement = studentElement.querySelector('.attendance-status');

                if (statusElement) {
                    statusElement.style.display = 'block';
                    const badge = statusElement.querySelector('.badge');

                    if (badge) {
                        if (present) {
                            badge.textContent = 'Présent (saisie manuelle)';
                            badge.className = 'badge bg-success';
                        } else {
                            badge.textContent = 'Absent (saisie manuelle)';
                            badge.className = 'badge bg-danger';
                        }
                    }
                }
            } else {
                alert(data.message || 'Erreur lors de l\'enregistrement de la présence');
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            alert('Erreur de connexion au serveur');
        });
    };

    // Set up event listeners
    if (startCameraButton) {
        startCameraButton.addEventListener('click', startCamera);
    }
    
    if (scheduleSelect) {
        scheduleSelect.addEventListener('change', function() {
            if (this.value !== "" && scheduleWarning) {
                scheduleWarning.style.display = 'none';
            }
        });
    }

    // Ensure camera is stopped when user leaves the page
    window.addEventListener('beforeunload', stopCamera);
});
