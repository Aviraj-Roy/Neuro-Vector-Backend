from app.ocr.batch_preprocessor import preprocess_images_in_dir

processed_images = preprocess_images_in_dir("uploads/")

for img in processed_images:
    print("Processed image:", img)
