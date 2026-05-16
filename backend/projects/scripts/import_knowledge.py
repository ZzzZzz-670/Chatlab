"""
对话实验室知识库导入脚本
将所有知识库文档导入向量知识库
"""
import os
import glob
from coze_coding_dev_sdk import KnowledgeClient, Config, KnowledgeDocument, DataSourceType, ChunkConfig
from coze_coding_utils.runtime_ctx.context import new_context

ASSETS_DIR = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects"), "assets")
TABLE_NAME = "coze_doc_knowledge"


def import_all_documents():
    ctx = new_context(method="import_knowledge")
    config = Config()
    client = KnowledgeClient(config=config, ctx=ctx)

    # 读取所有已解析的txt文档
    txt_files = sorted(glob.glob(os.path.join(ASSETS_DIR, "doc_*.txt")))
    if not txt_files:
        print("No document files found in assets/")
        return

    documents = []
    for filepath in txt_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            print(f"Skip empty file: {os.path.basename(filepath)}")
            continue
        # 文件名作为标题前缀，帮助识别来源
        basename = os.path.basename(filepath).replace("doc_", "").replace(".txt", "")
        wrapped = f"【{basename}】\n{content}"
        documents.append(KnowledgeDocument(source=DataSourceType.TEXT, raw_data=wrapped))
        print(f"Prepared: {basename} ({len(wrapped)} chars)")

    if not documents:
        print("No valid documents to import")
        return

    chunk_config = ChunkConfig(
        separator="\n\n",
        max_tokens=1500,
        remove_extra_spaces=True,
    )

    response = client.add_documents(
        documents=documents,
        table_name=TABLE_NAME,
        chunk_config=chunk_config,
    )

    if response.code == 0:
        print(f"Successfully imported {len(documents)} documents. IDs: {response.doc_ids}")
    else:
        print(f"Import failed: {response.msg}")


if __name__ == "__main__":
    import_all_documents()
