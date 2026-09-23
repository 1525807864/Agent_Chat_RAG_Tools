"""应用用例层：每个 UseCase 对应一种业务能力（SRP）。

依赖规则：use_cases → AgentApplication 上的共享依赖（过渡期）；
编排层只依赖 UseCase.execute → RunResult，不直接写 mode if/else 业务细节。
"""
