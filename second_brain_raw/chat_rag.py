"""
RAG (Retrieval Augmented Generation) chat module for processing and querying text documents
using LangChain and OpenAI.
"""

from IPython.display import display, Markdown
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.retrieval import create_retrieval_chain
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from unstructured.chunking.title import chunk_by_title
from unstructured.partition.text import partition_text
from unstructured.staging.base import dict_to_elements

# Constants
FILENAME = r"E:\SynologyDrive\4收藏\sissy\daughter_shan_part2.txt"
SYSTEM_PROMPT = (
    "你是一个AI助手，作为小说的说书人，根据小说内容来回答问题。"
    "Use the given context to answer the question. "
    "If you don't know the answer, say you don't know. "
    "Context: {context}"
)

embeddings = OpenAIEmbeddings(
      base_url="https://api.gptsapi.net/v1",
      api_key="sk-S2P177370c93a599f42dfdaa57ddf7d842ba6c34ffbOFQ3Y")

elements = partition_text(filename=FILENAME)
element_dict = [el.to_dict() for el in elements]

elements = dict_to_elements(element_dict)

chunks = chunk_by_title(
    elements,
    combine_text_under_n_chars=100,
    max_characters=3000,
)

documents = []
for element in chunks:
    metadata = element.metadata.to_dict()
    del metadata["languages"]
    metadata["source"] = metadata["filename"]
    documents.append(Document(page_content=element.text, metadata=metadata))

# vectorstore = Chroma.from_documents(documents, embeddings)

# 直接读取本地已有的数据库而不是重建
vectorstore = Chroma(persist_directory="./chroma", embedding_function=embeddings)
# vectorstore = Chroma.from_documents(documents, embeddings,persist_directory='./chroma')

retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 3}
    # search_type="similarity",
    # search_kwargs={"k": 2, "filter": {"creator": "AI"}}
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
    ]
)

llm = ChatOpenAI(
    openai_api_base="https://api.gptsapi.net/v1",
    openai_api_key="sk-S2P177370c93a599f42dfdaa57ddf7d842ba6c34ffbOFQ3Y",
    # model_name='gpt-4o-2024-05-13',
    model_name='gpt-4o-mini',
    temperature=0
)

question_answer_chain = create_stuff_documents_chain(llm, prompt)

chain = create_retrieval_chain(retriever, question_answer_chain)

result = chain.invoke({"input": '介绍一下姗姗'})
display(Markdown(result['answer']))
