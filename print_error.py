with open('backend/error.txt', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
    # Print in chunks to avoid truncation
    chunk_size = 500
    for i in range(0, len(content), chunk_size):
        print(content[i:i+chunk_size])
        print("=" * 50)
