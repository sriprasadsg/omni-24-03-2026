"""Test script to analyze PDF content"""
import os
import glob

def analyze_pdf(filepath):
    """Analyze a PDF file to see if it has content"""
    print(f"\n{'='*60}")
    print(f"Analyzing: {filepath}")
    print(f"{'='*60}")
    
    # Check file size
    size = os.path.getsize(filepath)
    print(f"File size: {size:,} bytes")
    
    # Read binary content
    with open(filepath, 'rb') as f:
        content = f.read()
    
    # Check for various PDF markers
    has_catalog = b'/Catalog' in content
    has_pages = b'/Pages' in content
    has_font = b'/Font' in content
    has_helvetica = b'Helvetica' in content
    has_text_object = b'BT' in content and b'ET' in content  # Begin/End Text
    has_tj = b'Tj' in content or b'TJ' in content  # Text showing operators
    
    print(f"Has /Catalog: {has_catalog}")
    print(f"Has /Pages: {has_pages}")
    print(f"Has /Font: {has_font}")
    print(f"Has Helvetica font: {has_helvetica}")
    print(f"Has text objects (BT...ET): {has_text_object}")
    print(f"Has text operators (Tj/TJ): {has_tj}")
    
    # Count occurrences of key terms
    text_streams = content.count(b'stream')
    print(f"Number of streams: {text_streams}")
    
    # Try to find readable text
    potential_text = []
    for line in content.split(b'\n')[:100]:  # First 100 lines
        if b'SOC' in line or b'Compliance' in line or b'Control' in line:
            try:
                potential_text.append(line.decode('latin-1', errors='ignore'))
            except:
                pass
    
    if potential_text:
        print(f"\nFound potential text content:")
        for text in potential_text[:5]:
            print(f"  - {text[:80]}")
    else:
        print("\nNo readable text content found in first 100 lines")
    
    print(f"\nFirst 200 bytes (hex): {content[:200].hex()[:400]}")

# Find and analyze PDFs
pdf_dir = "static/reports"
pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")), 
                   key=os.path.getmtime, reverse=True)

print(f"Found {len(pdf_files)} PDF files")

# Analyze the 2 most recent PDFs
for pdf_file in pdf_files[:2]:
    analyze_pdf(pdf_file)
