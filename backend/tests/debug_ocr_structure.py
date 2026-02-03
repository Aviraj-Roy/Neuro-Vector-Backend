from paddleocr import PaddleOCR
import os

ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)

# Test with first image
images_dir = "uploads/processed"
image_files = sorted([f for f in os.listdir(images_dir) if f.startswith("Bill_page_") and f.endswith(".png")])

if image_files:
    img_path = os.path.join(images_dir, image_files[0])
    print(f"Testing with: {img_path}")
    print(f"File exists: {os.path.exists(img_path)}")
    print(f"File size: {os.path.getsize(img_path)} bytes\n")
    
    result = ocr(img_path) # type: ignore
    
    print(f"Result type: {type(result)}")
    print(f"Result length: {len(result) if result else 0}\n")
    
    if result and len(result) > 0:
        page = result[0]
        print(f"Page type: {type(page)}")
        print(f"Page length: {len(page) if page else 0}\n")
        
        if page and len(page) > 0:
            print("First 3 detections:")
            for i, detection in enumerate(page[:3]):
                print(f"\nDetection {i+1}:")
                print(f"  Type: {type(detection)}")
                print(f"  Length: {len(detection)}")
                print(f"  Content: {detection}")
                
                if len(detection) >= 2:
                    box = detection[0]
                    text_info = detection[1]
                    print(f"\n  Box type: {type(box)}")
                    print(f"  Box value: {box}")
                    print(f"\n  Text info type: {type(text_info)}")
                    print(f"  Text info value: {text_info}")
else:
    print("No images found!")