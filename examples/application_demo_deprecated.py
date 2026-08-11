import os
from dotenv import load_dotenv
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser,JsonOutputParser

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
if __name__ == '__main__':
    # 加载环境变量

    llm = ChatOpenAI(
        model="deepseek-chat",
        temperature=0.7,
        openai_api_base="https://api.deepseek.com"
    )

    promet = ChatPromptTemplate.from_messages([
        ("system", "你是一个{role},用{style}风格回答"),
        ("human", "{question}")
    ])

    parser = JsonOutputParser()
    # 构建完整管道
    chain = promet | llm | parser
    result = chain.invoke({
        "role": "技术专家",
        "style": "简洁明了",
        "question": "解释什么是RAG"
    })


