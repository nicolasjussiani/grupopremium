import os

def replace_in_files(directory, old_text, new_text):
    for root, dirs, files in os.walk(directory):
        # Ignore some directories
        if '.git' in root or '__pycache__' in root or '.venv' in root:
            continue
        for file in files:
            if file.endswith(('.py', '.html', '.css', '.txt', '.md')):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if old_text in content:
                        new_content = content.replace(old_text, new_text)
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        print(f"Updated {filepath}")
                except Exception as e:
                    print(f"Could not process {filepath}: {e}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    replace_in_files(base_dir, "Grupo PremiumBR", "Grupo PremiumBRBR")
    replace_in_files(base_dir, "GRUPO PREMIUMBR", "GRUPO PREMIUMBRBR")
    replace_in_files(base_dir, "grupo premiumbr", "grupo premiumbrbr")
    print("Done renaming!")
