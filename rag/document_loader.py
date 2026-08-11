"""多格式文档加载器

知识点:
1. LangChain Document Loader 体系: 每种格式有专用 loader
2. RecursiveCharacterTextSplitter: 按优先级分隔符递归切分, 保持语义完整
3. 统一接口 + 元数据标准化: 所有格式输出一致的 Document 对象
"""

from pathlib import Path
from langchain_core.documents import Document


class DocumentLoader:
    """统一文档加载器, 支持 PDF / TXT / Markdown / HTML / CSV / JSON"""

    SUPPORTED_SUFFIXES = {
        ".pdf": "pypdf",
        ".txt": "text",
        ".md": "text",
        ".html": "html",
        ".csv": "csv",
        ".json": "json",
    }

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load_file(self, file_path: str | Path) -> list[Document]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_SUFFIXES:
            raise ValueError(f"不支持的文件格式: {suffix}, 支持: {list(self.SUPPORTED_SUFFIXES)}")

        loaders = {
            ".pdf": self._load_pdf,
            ".txt": self._load_text,
            ".md": self._load_text,
            ".html": self._load_html,
            ".csv": self._load_csv,
            ".json": self._load_json,
        }
        return loaders[suffix](path)

    def load_directory(self, dir_path: str | Path, recursive: bool = True) -> list[Document]:
        path = Path(dir_path)
        if not path.is_dir():
            raise NotADirectoryError(f"目录不存在: {dir_path}")

        docs = []
        pattern = "**/*" if recursive else "*"
        for file_path in path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_SUFFIXES:
                try:
                    docs.extend(self.load_file(file_path))
                except Exception as e:
                    print(f"警告: 加载 {file_path} 失败: {e}")
        return docs

    # ---- 各格式加载器 ----

    def _load_pdf(self, path: Path) -> list[Document]:
        from langchain_community.document_loaders import PyPDFLoader
        loader = PyPDFLoader(str(path))
        return loader.load_and_split(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    def _load_text(self, path: Path) -> list[Document]:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        text = path.read_text(encoding="utf-8")
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", "。", ".", " ", ""],
        )
        return splitter.create_documents([text], [{"source": str(path)}])

    def _load_html(self, path: Path) -> list[Document]:
        from bs4 import BeautifulSoup
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap
        )
        return splitter.create_documents([text], [{"source": str(path)}])

    def _load_csv(self, path: Path) -> list[Document]:
        import csv
        docs = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                content = " | ".join(f"{k}: {v}" for k, v in row.items())
                docs.append(Document(
                    page_content=content,
                    metadata={"source": str(path), "row": i},
                ))
        return docs

    def _load_json(self, path: Path) -> list[Document]:
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [Document(
                page_content=json.dumps(item, ensure_ascii=False),
                metadata={"source": str(path), "index": i},
            ) for i, item in enumerate(data)]
        elif isinstance(data, dict):
            return [Document(
                page_content=json.dumps(data, ensure_ascii=False),
                metadata={"source": str(path)},
            )]
        return []
