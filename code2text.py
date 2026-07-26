import os

def collect_python_files(folder_paths, output_file="combined_code.txt"):
    """
    Collects all .py files from given folders (recursively)
    and writes their contents into a single text file.
    """

    folder_paths = folder_paths if isinstance(folder_paths, list) else [folder_paths]

    with open(output_file, "w", encoding="utf-8") as out:
        for folder in folder_paths:
            if not os.path.exists(folder):
                print(f"[WARNING] Folder not found: {folder}")
                continue

            for root, dirs, files in os.walk(folder):
                for file in files:
                    if file.endswith(".py"):
                        file_path = os.path.join(root, file)

                        out.write("\n" + "="*80 + "\n")
                        out.write(f"FILE: {file_path}\n")
                        out.write("="*80 + "\n\n")

                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                out.write(f.read())
                        except Exception as e:
                            out.write(f"[ERROR reading file]: {e}\n")

    print(f"\n✔ Combined text file generated: {output_file}")


if __name__ == "__main__":
    # 🔹 Example usage:
    folders = [
        "backend",
        "config",
        "Data_ingestion",
        "stratergies",
        "backtest",
        "data", 
        "UI"
    ]

    collect_python_files(folders, output_file="all_python_code.txt")