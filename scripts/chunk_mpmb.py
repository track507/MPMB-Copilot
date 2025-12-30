"""
MPMB Source Code Chunker
Extracts semantic chunks from MPMB JavaScript files for RAG indexing

Run from project root: python scripts/chunk_mpmb.py
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# Paths (relative to project root)
MPMB_SOURCE = Path("./data/mpmb_source")
SYNTAX_DIR = MPMB_SOURCE / "additional content syntax"
OUTPUT_DIR = Path("./data/chunked_output")

# Create output directory
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class CodeChunk:
    """Represents a single chunk of code"""
    content: str
    source_file: str
    chunk_index: int
    start_line: int
    end_line: int
    chunk_type: str  # "template_attribute", "function", "object_literal", "comment_block"
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class TemplateAttributeExtractor:
    """Extracts individual attributes from MPMB template files"""

    # Pattern to match: attributeName : value, followed by /* comment */
    ATTRIBUTE_PATTERN = re.compile(
        r'(\w+)\s*:\s*(.+?),?\s*\n\s*/\*\s*(.*?)\s*\*/',
        re.DOTALL
    )

    # Pattern to extract OPTIONAL/REQUIRED from comment
    REQUIRED_PATTERN = re.compile(r'//\s*(OPTIONAL|REQUIRED)\s*//')

    # Pattern to extract TYPE from comment
    TYPE_PATTERN = re.compile(r'TYPE:\s*([^\n]+)')

    # Pattern to extract USE from comment
    USE_PATTERN = re.compile(r'USE:\s*([^\n]+)')

    # Pattern to extract category headers
    CATEGORY_PATTERN = re.compile(r'//\s*>>>(.+?)>>>\s*//')

    def extract_attributes(self, filepath: Path) -> List[CodeChunk]:
        """Extract all documented attributes from a template file"""
        chunks = []

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')

        # Find categories
        current_category = "Uncategorized"
        category_map = {}  # line_num -> category

        for i, line in enumerate(lines):
            cat_match = self.CATEGORY_PATTERN.search(line)
            if cat_match:
                current_category = cat_match.group(1).strip()
                category_map[i] = current_category

        # Extract attributes with their comments
        for chunk_index, match in enumerate(self.ATTRIBUTE_PATTERN.finditer(content)):
            attr_name = match.group(1)
            attr_example = match.group(2)
            attr_comment = match.group(3)

            # Calculate line numbers
            start_pos = match.start()
            end_pos = match.end()
            start_line = content[:start_pos].count('\n') + 1
            end_line = content[:end_pos].count('\n') + 1

            # Find the category for this attribute
            category = "Uncategorized"
            for cat_line, cat_name in sorted(category_map.items(), reverse=True):
                if cat_line < start_line:
                    category = cat_name
                    break

            # Extract metadata from comment
            is_required = bool(self.REQUIRED_PATTERN.search(attr_comment))

            type_match = self.TYPE_PATTERN.search(attr_comment)
            attr_type = type_match.group(1).strip() if type_match else "unknown"

            use_match = self.USE_PATTERN.search(attr_comment)
            attr_use = use_match.group(1).strip() if use_match else ""

            # Create chunk
            chunk_content = f"{attr_name} : {attr_example.strip()},\n/* {attr_comment} */"

            chunk = CodeChunk(
                content=chunk_content,
                source_file=str(filepath.relative_to(MPMB_SOURCE)),
                chunk_index=chunk_index,
                start_line=start_line,
                end_line=end_line,
                chunk_type="template_attribute",
                metadata={
                    "attribute_name": attr_name,
                    "is_required": is_required,
                    "attribute_type": attr_type,
                    "usage": attr_use,
                    "category": category,
                    "example": attr_example.strip()[:100],  # First 100 chars
                    "file_type": "syntax_template",
                }
            )

            chunks.append(chunk)

        return chunks


class WorkingCodeExtractor:
    """Extracts complete functions and objects from working MPMB code files"""

    # Pattern to match function definitions
    FUNCTION_PATTERN = re.compile(
        r'(?:^|\n)((?:\/\*\*[\s\S]*?\*\/\s*)?function\s+(\w+)\s*\([^)]*\)\s*\{)',
        re.MULTILINE
    )

    # Pattern to match object assignments
    OBJECT_PATTERN = re.compile(
        r'(\w+(?:\[[\'"]\w+[\'"]\])?)\s*=\s*\{',
        re.MULTILINE
    )

    def extract_functions(self, content: str, filepath: Path) -> List[CodeChunk]:
        """Extract complete function definitions"""
        chunks = []
        lines = content.split('\n')

        for chunk_index, match in enumerate(self.FUNCTION_PATTERN.finditer(content)):
            func_name = match.group(2)
            start_pos = match.start()
            start_line = content[:start_pos].count('\n') + 1

            # Find matching closing brace
            brace_count = 0
            in_function = False
            end_pos = start_pos

            for i in range(start_pos, len(content)):
                char = content[i]
                if char == '{':
                    brace_count += 1
                    in_function = True
                elif char == '}':
                    brace_count -= 1
                    if in_function and brace_count == 0:
                        end_pos = i + 1
                        break

            if end_pos > start_pos:
                end_line = content[:end_pos].count('\n') + 1
                func_content = content[start_pos:end_pos]

                # Check if there's JSDoc before the function
                jsdoc_start = max(0, start_pos - 500)  # Look back up to 500 chars
                preceding_text = content[jsdoc_start:start_pos]
                jsdoc_match = re.search(r'(/\*\*[\s\S]*?\*/)\s*$', preceding_text)

                if jsdoc_match:
                    jsdoc = jsdoc_match.group(1)
                    func_content = jsdoc + '\n' + func_content
                    jsdoc_start_pos = jsdoc_start + jsdoc_match.start()
                    start_line = content[:jsdoc_start_pos].count('\n') + 1

                chunk = CodeChunk(
                    content=func_content,
                    source_file=str(filepath.relative_to(MPMB_SOURCE)),
                    chunk_index=chunk_index,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type="function",
                    metadata={
                        "function_name": func_name,
                        "has_jsdoc": jsdoc_match is not None,
                        "file_type": "working_code",
                        "size_lines": end_line - start_line + 1,
                    }
                )

                chunks.append(chunk)

        return chunks

    def extract_objects(self, content: str, filepath: Path, max_lines: int = 100) -> List[CodeChunk]:
        """Extract object literal assignments (limited to reasonable size)"""
        chunks = []

        for chunk_index, match in enumerate(self.OBJECT_PATTERN.finditer(content)):
            obj_name = match.group(1)
            start_pos = match.start()
            start_line = content[:start_pos].count('\n') + 1

            # Find matching closing brace
            brace_count = 0
            in_object = False
            end_pos = start_pos

            for i in range(start_pos, len(content)):
                char = content[i]
                if char == '{':
                    brace_count += 1
                    in_object = True
                elif char == '}':
                    brace_count -= 1
                    if in_object and brace_count == 0:
                        end_pos = i + 1
                        break

            if end_pos > start_pos:
                end_line = content[:end_pos].count('\n') + 1

                # Skip if object is too large (likely a huge list)
                if (end_line - start_line) > max_lines:
                    continue

                obj_content = content[start_pos:end_pos]

                chunk = CodeChunk(
                    content=obj_content,
                    source_file=str(filepath.relative_to(MPMB_SOURCE)),
                    chunk_index=chunk_index,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type="object_literal",
                    metadata={
                        "object_name": obj_name,
                        "file_type": "working_code",
                        "size_lines": end_line - start_line + 1,
                    }
                )

                chunks.append(chunk)

        return chunks


class MPMBChunker:
    """Main chunker orchestrator"""

    def __init__(self):
        self.template_extractor = TemplateAttributeExtractor()
        self.code_extractor = WorkingCodeExtractor()
        self.stats = {
            "files_processed": 0,
            "chunks_created": 0,
            "template_chunks": 0,
            "function_chunks": 0,
            "object_chunks": 0,
        }

    def chunk_template_file(self, filepath: Path) -> List[CodeChunk]:
        """Chunk a template/syntax file"""
        print(f"  Processing template: {filepath.name}")
        chunks = self.template_extractor.extract_attributes(filepath)
        self.stats["template_chunks"] += len(chunks)
        return chunks

    def chunk_working_file(self, filepath: Path) -> List[CodeChunk]:
        """Chunk a working code file"""
        print(f"  Processing code file: {filepath.name}")

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        chunks = []

        # Extract functions
        func_chunks = self.code_extractor.extract_functions(content, filepath)
        chunks.extend(func_chunks)
        self.stats["function_chunks"] += len(func_chunks)

        # Extract objects (limit to 100 lines to avoid huge lists)
        obj_chunks = self.code_extractor.extract_objects(content, filepath, max_lines=100)
        chunks.extend(obj_chunks)
        self.stats["object_chunks"] += len(obj_chunks)

        return chunks

    def chunk_directory(self, directory: Path, is_template: bool = False) -> List[CodeChunk]:
        """Chunk all JS files in a directory"""
        all_chunks = []

        js_files = list(directory.glob("*.js"))
        print(f"\nProcessing {len(js_files)} files in {directory.name}/")

        for filepath in js_files:
            try:
                if is_template:
                    chunks = self.chunk_template_file(filepath)
                else:
                    chunks = self.chunk_working_file(filepath)

                all_chunks.extend(chunks)
                self.stats["files_processed"] += 1
                self.stats["chunks_created"] += len(chunks)

            except Exception as e:
                print(f"    ERROR processing {filepath.name}: {e}")

        return all_chunks

    def save_chunks(self, chunks: List[CodeChunk], output_file: str):
        """Save chunks to JSON file"""
        output_path = OUTPUT_DIR / output_file

        # Convert to dicts for JSON
        chunks_data = [chunk.to_dict() for chunk in chunks]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(chunks_data, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {len(chunks)} chunks to {output_path}")

    def print_stats(self):
        """Print chunking statistics"""
        print("\n" + "="*60)
        print("CHUNKING STATISTICS")
        print("="*60)
        print(f"Files processed:     {self.stats['files_processed']}")
        print(f"Total chunks:        {self.stats['chunks_created']}")
        print(f"  Template chunks:   {self.stats['template_chunks']}")
        print(f"  Function chunks:   {self.stats['function_chunks']}")
        print(f"  Object chunks:     {self.stats['object_chunks']}")
        print("="*60)


def main():
    """Main chunking workflow"""
    chunker = MPMBChunker()

    print("="*60)
    print("MPMB SOURCE CODE CHUNKER")
    print("="*60)

    # 1. Chunk template/syntax files (HIGHEST PRIORITY)
    print("\n[1/3] Chunking Template Files...")
    template_chunks = chunker.chunk_directory(SYNTAX_DIR, is_template=True)
    chunker.save_chunks(template_chunks, "template_chunks.json")

    # 2. Chunk _functions directory (CORE ENGINE)
    print("\n[2/3] Chunking Core Functions...")
    functions_dir = MPMB_SOURCE / "_functions"
    if functions_dir.exists():
        function_chunks = chunker.chunk_directory(functions_dir, is_template=False)
        chunker.save_chunks(function_chunks, "function_chunks.json")

    # 3. Chunk additional content (EXAMPLES)
    print("\n[3/3] Chunking Additional Content Examples...")
    content_dir = MPMB_SOURCE / "additional content"
    content_chunks = []

    if content_dir.exists():
        # Process subdirectories
        for subdir in content_dir.iterdir():
            if subdir.is_dir() and subdir.name != "syntax":
                chunks = chunker.chunk_directory(subdir, is_template=False)
                content_chunks.extend(chunks)

    if content_chunks:
        chunker.save_chunks(content_chunks, "content_chunks.json")

    # Print final statistics
    chunker.print_stats()

    # Sample output
    print("\n" + "="*60)
    print("SAMPLE CHUNKS (first 3 template chunks)")
    print("="*60)
    for i, chunk in enumerate(template_chunks[:3], 1):
        print(f"\n[{i}] {chunk.metadata.get('attribute_name', 'Unknown')}")
        print(f"    File: {chunk.source_file}")
        print(f"    Type: {chunk.metadata.get('attribute_type', 'Unknown')}")
        print(f"    Category: {chunk.metadata.get('category', 'Unknown')}")
        print(f"    Lines: {chunk.start_line}-{chunk.end_line}")
        print(f"    Content preview: {chunk.content[:150]}...")


if __name__ == "__main__":
    main()
