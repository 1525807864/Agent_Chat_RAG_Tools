"""Cursor 本地Agent的一次问答，服务器里必须用异步客户端，否则会阻塞"""
from __future__ import annotations 
from cursor_sdk import AsyncClient,CursorAgentError,LocalAgentOptions

class CursorRunner:
    """打开本地agent，发送一句话，返回最终文本和新的agent_id"""
    def __init__(self,api_key:str,model:str,cwd:str)->None:
        self._api_key = api_key  
        self._model = model  
        self._cwd = cwd   
    async def ask(self,prompt:str,agent_id:str)->tuple[str,str]:
        """有 agent_id 就 resume，没有或 resume 失败就新建。
        返回 (回答文本, agent_id)。agent_id 交给 agent_store 保存。
        CursorAgentError 表示没跑起来（密钥、网络），让上层退回 DeepSeek。
        status == error 表示已经跑了但失败，把错误原文抛出去，不要假装成功。
        """
        async with await AsyncClient.launch_bridge(workspace=self._cwd) as client:
            agent = await self._open(client, agent_id)
            try:
                run = await agent.send(prompt)
                # text() 会等到结束；只拿助手最终文本，不把工具过程塞进聊天气泡。
                answer = await run.text()
                done = await run.wait()
                if getattr(done, "status", "") == "error":
                    raise RuntimeError(answer or "Cursor运行失败")
                return answer or "", agent.agent_id
            finally:
                await agent.close()
    
    async def _open(self,client,agent_id:str):
        local = LocalAgentOptions(cwd=self._cwd)
        if agent_id:
            try:
                return await client.agents.resume(
                    agent_id,
                    model=self._model,
                    api_key=self._api_key,
                    local=local,
                )
            except CursorAgentError:
                #旧id失败就重建，不把这次失败当成整轮失败
                pass 
        return await client.agents.create(
            model=self._model,
            api_key=self._api_key,
            local=local,
        )