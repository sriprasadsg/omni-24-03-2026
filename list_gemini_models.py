import google.generativeai as genai
import os

API_KEY = "AIzaSyDVN6ccV7gcKa7NXPmumok-XPOKi6TjdeM"

def list_models():
    print("Configuring...")
    genai.configure(api_key=API_KEY)
    
    print("Listing models to models.txt...")
    try:
        with open("models.txt", "w", encoding="utf-8") as f:
            count = 0
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    f.write(f"Name: {m.name}\n")
                    f.write("-" * 20 + "\n")
                    count += 1
            f.write(f"Total: {count}\n")
        print(f"Success. Found {count} models.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_models()
