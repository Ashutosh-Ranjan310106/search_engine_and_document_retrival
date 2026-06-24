import os

dataset_dir = r"C:\Users\rrpra\Documents\Github\search_engine_and_document_retrival"
exclude_folders = {"venv", "frontend", "hooks", "fat_report", "dist", "build", "Ollama", ".git"}

def print_tree(path, prefix=""):
    entries = sorted(
        [e for e in os.listdir(path)
         if not (os.path.isdir(os.path.join(path, e)) and e in exclude_folders)]
    )

    for i, entry in enumerate(entries):
        full_path = os.path.join(path, entry)
        connector = "└── " if i == len(entries) - 1 else "├── "

        print(prefix + connector + entry)

        if os.path.isdir(full_path):
            extension = "    " if i == len(entries) - 1 else "│   "
            print_tree(full_path, prefix + extension)

print(os.path.basename(dataset_dir))
print_tree(dataset_dir)