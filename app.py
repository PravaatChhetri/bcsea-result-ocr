from flask import Flask, request, jsonify, render_template_string
import os
import tempfile
import base64
from werkzeug.utils import secure_filename

try:
    import pytesseract
    import cv2
    import pandas as pd
    from pytesseract import Output
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

app = Flask(__name__)
UPLOAD_FOLDER = tempfile.gettempdir()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DIGIT_WORD_MAP = {
    'ZERO': '0', 'ONE': '1', 'TWO': '2', 'THREE': '3', 'FOUR': '4',
    'FIVE': '5', 'SIX': '6', 'SEVEN': '7', 'EIGHT': '8', 'NINE': '9'
}
KNOWN_SUBJECT_KEYWORDS = [
    'ENGLISH', 'DZONGKHA', 'HISTORY', 'CIVICS', 'GEOGRAPHY',
    'MATHS', 'SCIENCE', 'COMPUTER', 'APPLICATIONS', 'PHYSICS', 'CHEMISTRY', 'MATHEMATICS'
]

def words_to_number(words):
    num_str = ''.join(DIGIT_WORD_MAP.get(w.upper(), '') for w in words if w.upper() in DIGIT_WORD_MAP)
    return int(num_str) if num_str.isdigit() else None

def merge_subject_keywords(line_words):
    full_line = ' '.join(line_words).upper()
    subjects = [kw for kw in KNOWN_SUBJECT_KEYWORDS if kw in full_line]
    return ' '.join(sorted(set(subjects))) if subjects else None

def extract_digit_word_marks(words):
    digit_words = [w.upper() for w in words if w.upper() in DIGIT_WORD_MAP]
    if len(digit_words) >= 2:
        return words_to_number(digit_words[:3])
    return None

def extract_data_from_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return {'error': 'Could not read image file'}

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    data = pytesseract.image_to_data(thresh, output_type=Output.DATAFRAME)
    data = data[(data.conf > 0) & (data.text.str.strip() != '')].reset_index(drop=True)
    lines = data.groupby('line_num')

    extracted_subjects = []
    name = None

    name_line = data[data['text'].str.contains('Name', case=False, na=False)]
    if not name_line.empty:
        idx = name_line.index[0]
        parts = data.loc[idx+1:idx+4, 'text'].tolist()
        name = ' '.join([w.title() for w in parts if w.isalpha()])

    for line_num, group in lines:
        words = group.sort_values('left')['text'].tolist()
        subject = merge_subject_keywords(words)
        if not subject:
            continue
        all_words = list(words)
        if (line_num + 1) in lines.groups:
            all_words += data[data['line_num'] == (line_num + 1)]['text'].tolist()
        word_based_mark = extract_digit_word_marks(all_words)
        digit_marks = [int(w) for w in all_words if w.isdigit() and 30 <= int(w) <= 100]
        mark = word_based_mark or (digit_marks[0] if digit_marks else None)
        if mark:
            subject_name = ' '.join(sorted(set(subject.title().split())))
            if not any(s['subject'] == subject_name for s in extracted_subjects):
                extracted_subjects.append({"subject": subject_name, "marks": mark})

    return clean_result_data({
        'name': name,
        'subjects': extracted_subjects
    })

def clean_result_data(raw_result):
    cleaned = {
        'name': None,
        'subjects': []
    }
    name = raw_result.get('name', '')
    if name:
        name_parts = name.split()
        name_cleaned = [part for part in name_parts if part.upper() not in {'INDEX', 'NO', 'CERTIFICATE'}]
        cleaned['name'] = ' '.join(name_cleaned).strip().title()

    for subject in raw_result.get('subjects', []):
        mark = subject['marks']
        if mark > 100:
            mark = int(str(mark)[:2])
        if 30 <= mark <= 100:
            cleaned['subjects'].append({
                'subject': subject['subject'].title(),
                'marks': mark
            })

    return cleaned

@app.route('/', methods=['GET', 'POST'])
def index():
    example_triggered = request.form.get("example") == "true"
    if request.method == 'POST':
        if example_triggered:
            # Load example image from static folder
            path = os.path.join(app.root_path, "static", "example.png")
            filename = "example.png"
        else:
            if 'file' not in request.files:
                return jsonify({'error': 'No file uploaded'})
            file = request.files['file']
            filename = secure_filename(file.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(path)
        # if 'file' not in request.files:
        #     return jsonify({'error': 'No file uploaded'})

        # file = request.files['file']
        # filename = secure_filename(file.filename)
        # path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        # file.save(path)
        
        # Convert image to base64 for display
        with open(path, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        
        data = extract_data_from_image(path)
        data['image_data'] = img_base64
        data['image_filename'] = filename
        
        if os.path.exists(path):
            os.remove(path)

        # Results page with minimalistic design
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Results</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                .error {
                    color: #dc3545;
                    background: #f8d7da;
                    border: 1px solid #f5c6cb;
                    padding: 16px;
                    border-radius: 6px;
                    text-align: center;
                    margin-bottom: 24px;
                }
                
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #fafafa;
                    color: #333;
                    line-height: 1.6;
                    padding: 40px 20px;
                }
                
                .container {
                    max-width: 1000px;
                    margin: 0 auto;
                }
                
                .content {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 32px;
                    align-items: start;
                }
                
                .header {
                    text-align: center;
                    margin-bottom: 40px;
                }
                
                .header h1 {
                    font-size: 1.5rem;
                    font-weight: 600;
                    color: #1a1a1a;
                    margin-bottom: 8px;
                }
                
                .header p {
                    color: #666;
                    font-size: 0.9rem;
                }
                
                .image-section {
                    position: sticky;
                    top: 20px;
                }
                
                .image-container {
                    background: white;
                    border-radius: 8px;
                    border: 1px solid #e5e5e5;
                    padding: 20px;
                    text-align: center;
                }
                
                .image-title {
                    font-size: 0.9rem;
                    color: #666;
                    margin-bottom: 16px;
                    font-weight: 500;
                }
                
                .uploaded-image {
                    max-width: 100%;
                    height: auto;
                    border-radius: 6px;
                    border: 1px solid #e5e5e5;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
                
                .image-info {
                    margin-top: 12px;
                    font-size: 0.8rem;
                    color: #999;
                }
                
                .student-name {
                    font-size: 1.25rem;
                    font-weight: 500;
                    color: #1a1a1a;
                    text-align: center;
                    margin-bottom: 32px;
                    padding-bottom: 16px;
                    border-bottom: 1px solid #f0f0f0;
                }
                
                .stats {
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 16px;
                    margin-bottom: 32px;
                }
                
                .stat {
                    text-align: center;
                    padding: 16px;
                    background: #f8f9fa;
                    border-radius: 6px;
                }
                
                .stat-value {
                    font-size: 1.5rem;
                    font-weight: 600;
                    color: #1a1a1a;
                    margin-bottom: 4px;
                }
                
                .stat-label {
                    font-size: 0.75rem;
                    color: #666;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                
                .subjects {
                    space-y: 12px;
                }
                
                .subject {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 16px 0;
                    border-bottom: 1px solid #f0f0f0;
                }
                
                .subject:last-child {
                    border-bottom: none;
                }
                
                .subject-name {
                    font-size: 0.95rem;
                    color: #1a1a1a;
                    font-weight: 400;
                }
                
                .subject-mark {
                    font-size: 1rem;
                    font-weight: 600;
                    color: #666;
                    background: #f5f5f5;
                    padding: 4px 12px;
                    border-radius: 20px;
                    min-width: 50px;
                    text-align: center;
                }
                
                .actions {
                    display: flex;
                    gap: 12px;
                    justify-content: center;
                    margin-top: 32px;
                }
                
                .btn {
                    padding: 10px 20px;
                    border: 1px solid #e5e5e5;
                    border-radius: 6px;
                    background: white;
                    color: #333;
                    text-decoration: none;
                    font-size: 0.9rem;
                    font-weight: 400;
                    cursor: pointer;
                    transition: all 0.2s ease;
                }
                
                .btn:hover {
                    background: #f8f9fa;
                    border-color: #d0d0d0;
                }
                
                .btn-primary {
                    background: #1a1a1a;
                    color: white;
                    border-color: #1a1a1a;
                }
                
                .btn-primary:hover {
                    background: #333;
                    border-color: #333;
                }
                
                .card {
                    background: white;
                    border-radius: 8px;
                    border: 1px solid #e5e5e5;
                    padding: 32px;
                    margin-bottom: 24px;
                }
                
                .results-section {
                    min-height: 400px;
                }
                
                @media (max-width: 480px) {
                    body { padding: 20px 16px; }
                    .card { padding: 24px 20px; }
                    .stats { grid-template-columns: 1fr; }
                    .actions { flex-direction: column; }
                    .image-container { padding: 16px; }
                }
                
                .no-results {
                    text-align: center;
                    color: #666;
                    font-size: 0.95rem;
                    padding: 40px 20px;
                }
                
                @media (max-width: 768px) {
                    .content {
                        grid-template-columns: 1fr;
                        gap: 24px;
                    }
                    
                    .image-section {
                        order: 2;
                        position: static;
                    }
                    
                    .results-section {
                        order: 1;
                    }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Academic Results</h1>
                    <p>OCR extraction complete</p>
                </div>
                
                <div class="content">
                    <div class="results-section">
                        <div class="card">
                            {% if data.get('error') %}
                                <div class="error">
                                    {{ data.error }}
                                </div>
                            {% else %}
                                <div class="student-name">
                                    {{ data.name if data.name else 'Student Name Not Found' }}
                                </div>
                                
                                {% if data.subjects %}
                                    {% set total_marks = data.subjects | sum(attribute='marks') %}
                                    {% set average = ((total_marks / data.subjects|length) / 5) | round(1) %}
                                    
                                    <div class="stats">
                                        <div class="stat">
                                            <div class="stat-value">{{ data.subjects|length }}</div>
                                            <div class="stat-label">Subjects</div>
                                        </div>
                                        <div class="stat">
                                            <div class="stat-value">{{ total_marks }}</div>
                                            <div class="stat-label">Total</div>
                                        </div>
                                        <div class="stat">
                                            <div class="stat-value">{{ average }}</div>
                                            <div class="stat-label">Grade</div>
                                        </div>
                                    </div>
                                    
                                    <div class="subjects">
                                        {% for subject in data.subjects %}
                                            <div class="subject">
                                                <div class="subject-name">{{ subject.subject }}</div>
                                                <div class="subject-mark">{{ subject.marks }}</div>
                                            </div>
                                        {% endfor %}
                                    </div>
                                {% else %}
                                    <div class="no-results">
                                        No grade information found in the image.
                                    </div>
                                {% endif %}
                            {% endif %}
                            
                            <div class="actions">
                                <a href="/" class="btn btn-primary">Upload Another</a>
                                <button onclick="window.print()" class="btn">Print</button>
                            </div>
                        </div>
                    </div>
                    
                    {% if data.get('image_data') %}
                    <div class="image-section">
                        <div class="image-container">
                            <div class="image-title">Uploaded Image</div>
                            <img src="data:image/jpeg;base64,{{ data.image_data }}" 
                                 alt="Uploaded academic result" 
                                 class="uploaded-image">
                            <div class="image-info">{{ data.image_filename }}</div>
                        </div>
                    </div>
                    {% endif %}
                </div>
            </div>
        </body>
        </html>
        """, data=data)

    # Upload page with minimalistic design
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>OCR Grade Extractor</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #fafafa;
                color: #333;
                line-height: 1.6;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 40px 20px;
            }
            
            .container {
                background: white;
                border-radius: 8px;
                border: 1px solid #e5e5e5;
                padding: 48px;
                max-width: 500px;
                width: 100%;
            }
            
            .header {
                text-align: center;
                margin-bottom: 40px;
            }
            
            .header h1 {
                font-size: 1.5rem;
                font-weight: 600;
                color: #1a1a1a;
                margin-bottom: 8px;
            }
            
            .header p {
                color: #666;
                font-size: 0.9rem;
            }
            
            .upload-area {
                border: 2px dashed #d0d0d0;
                border-radius: 8px;
                padding: 48px 24px;
                text-align: center;
                background: #fafafa;
                cursor: pointer;
                transition: all 0.2s ease;
                margin-bottom: 24px;
                position: relative;
            }
            
            .upload-area:hover,
            .upload-area.dragover {
                border-color: #999;
                background: #f5f5f5;
            }
            
            .upload-icon {
                font-size: 2rem;
                color: #999;
                margin-bottom: 16px;
                display: block;
            }
            
            .upload-text {
                font-size: 1rem;
                color: #1a1a1a;
                margin-bottom: 8px;
                font-weight: 500;
            }
            
            .upload-hint {
                color: #666;
                font-size: 0.85rem;
            }
            
            .file-input {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                opacity: 0;
                cursor: pointer;
            }
            
            .selected-file {
                background: #f0f9ff;
                border: 1px solid #bfdbfe;
                color: #1e40af;
                padding: 12px;
                border-radius: 6px;
                font-size: 0.9rem;
                margin-bottom: 16px;
                display: none;
            }
            
            .submit-btn {
                background: #1a1a1a;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.9rem;
                font-weight: 500;
                width: 100%;
                transition: background 0.2s ease;
                display: none;
            }
            
            .submit-btn:hover {
                background: #333;
            }
            
            .example-btn {
                background: #1a1a1a;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.9rem;
                font-weight: 500;
                width: 100%;
                transition: background 0.2s ease;
            }
            
            .example-btn:hover {
                background: #333;
            }
            
            .loading {
                display: none;
                text-align: center;
                margin-top: 16px;
            }
            
            .loading-spinner {
                width: 20px;
                height: 20px;
                border: 2px solid #f3f3f3;
                border-top: 2px solid #1a1a1a;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 12px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .loading p {
                color: #666;
                font-size: 0.9rem;
            }
            
            .features {
                margin-top: 32px;
                padding-top: 24px;
                border-top: 1px solid #f0f0f0;
            }
            
            .feature {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 16px;
            }
            
            .feature:last-child {
                margin-bottom: 0;
            }
            
            .feature-icon {
                font-size: 1.25rem;
                color: #666;
            }
            
            .feature-text {
                font-size: 0.85rem;
                color: #666;
            }
            .example-preview{
                width:100%,
                height: auto,
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                border: 1px solid #e5e5e5;
                padding: 10px;
                
            }
            @media (max-width: 480px) {
                .container {
                    padding: 32px 24px;
                }
                .upload-area {
                    padding: 32px 20px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Grade Extractor</h1>
                <p>Upload an image to extract academic results</p>
            </div>
            
            <form id="uploadForm" method="POST" enctype="multipart/form-data">
                <div class="upload-area" id="uploadArea">
                    <span class="upload-icon">📄</span>
                    <div class="upload-text">Select an image</div>
                    <div class="upload-hint">JPG, PNG, GIF, BMP supported</div>
                    <input type="file" name="file" class="file-input" id="fileInput" accept="image/*" required>
                </div>
                
                <div class="selected-file" id="selectedFile"></div>
                
                <button type="submit" class="submit-btn" id="submitBtn">
                    Extract Results
                </button>
                
                <div class="loading" id="loading">
                    <div class="loading-spinner"></div>
                    <p>Processing image...</p>
                </div>
            </form>
            
            <div class="example-preview">
                <form method="POST">
                    <input type="hidden" name="example" value="true">
                    <button type="submit" class="example-btn">📄 Try Example Image</button>
                </form>
                <br>
                <img src="/static/example.png" width = '200px'
                height='150px' alt="Example Image">
            </div>
            
            <div class="features">
                <div class="feature">
                    <span class="feature-icon">🔍</span>
                    <span class="feature-text">Automatic text recognition</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">📊</span>
                    <span class="feature-text">Grade extraction and analysis</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">⚡</span>
                    <span class="feature-text">Fast processing</span>
                </div>
            </div>
        </div>
        
        <script>
            const uploadArea = document.getElementById('uploadArea');
            const fileInput = document.getElementById('fileInput');
            const selectedFile = document.getElementById('selectedFile');
            const submitBtn = document.getElementById('submitBtn');
            const uploadForm = document.getElementById('uploadForm');
            const loading = document.getElementById('loading');
            
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });
            
            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });
            
            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    fileInput.files = files;
                    showSelectedFile(files[0]);
                }
            });
            
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    showSelectedFile(e.target.files[0]);
                }
            });
            
            function showSelectedFile(file) {
                selectedFile.innerHTML = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
                selectedFile.style.display = 'block';
                submitBtn.style.display = 'block';
            }
            
            uploadForm.addEventListener('submit', () => {
                submitBtn.style.display = 'none';
                loading.style.display = 'block';
            });
        </script>
        <footer>
        <!-- <p>Created by Pravaat Chhetri</p> -->
        </footer>
    </body>
    </html>
    """)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
