from app.ingestion.pdf_loader import pdf_to_images

image_paths = pdf_to_images("medicall_bill-2.pdf")
print(image_paths)
