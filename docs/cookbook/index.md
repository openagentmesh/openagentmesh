# Cookbook

Practical recipes for common AgentMesh patterns. Each recipe is self-contained with full code you can copy and run.

- [Multi-Process Agents](multi-process.md): Run provider and consumer as separate processes
- [Multi-Module Projects](multi-module.md): Organize agents across multiple files with a shared mesh instance
- [Shared Plan Coordination](shared-plan.md): Two agents coordinate on a shared plan via CAS
- [LLM-Driven Tool Selection](llm-tool-selection.md): Discover agents at runtime and expose them as tools to an LLM
- [Error Handling](error-handling.md): Catch errors, retry with backoff, fall back to alternative agents, and monitor the error stream
- [Automatic Load Balancing](load-balancing.md): Scale agents by running more copies; NATS queue groups distribute requests automatically
- [Reactive Pipeline](reactive-pipeline.md): Agents watch KV changes and trigger downstream work automatically, no orchestrator needed
- [Parallel RAG Indexing](parallel-rag-indexing.md): Multiple indexer agents split a large document and index chunks in parallel using ObjectStore and ChromaDB
