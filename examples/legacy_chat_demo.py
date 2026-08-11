import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.output_parsers import StrOutputParser

from llm_deepseek import DeepSeekChatModel
from config.settings import MODEL_NAME, MODEL_TEMPERATURE, MODEL_MAX_TOKENS

load_dotenv()

llm = DeepSeekChatModel(
    model_name=MODEL_NAME,
    temperature=MODEL_TEMPERATURE,
    max_tokens=MODEL_MAX_TOKENS,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个优秀的高级资深程序员,精通包括但不限于以下的能力"
               "- 具备强大的编程能力"
               "- 具备强大的编程知识分解以及编程架构能力"
               "- 包括但不限于软件架构以及面对对象的能力等等"),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}")
])

chain = prompt | llm | StrOutputParser()

store: dict[str, InMemoryChatMessageHistory] = {}


def get_session_history(session_id: str) -> InMemoryChatMessageHistory:
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]


chain_with_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history",
)


def chat_with_assistant():
    print("个人助手已启动! 输入'退出'或'quit'结束对话")
    print("-" * 50)

    while True:
        user_input = input("\n你: ").strip()

        if user_input.lower() in ['退出', 'quit', 'exit']:
            print("助手: 再见！很高兴为您服务！")
            break

        if not user_input:
            continue

        try:
            response = chain_with_history.invoke(
                {"input": user_input},
                config={"configurable": {"session_id": "default"}}
            )
            print(f"助手: {response}")

        except Exception as e:
            print(f"出错: {e}")


if __name__ == "__main__":
    chat_with_assistant()