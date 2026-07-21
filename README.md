# UX Benchmarks

> 场景级 UX 设计标杆发现与洞察工具 · 采集阶段

## 架构

- **后端**：Python FastAPI + Celery + PostgreSQL + Redis
- **前端**：Next.js 14 + TypeScript + Tailwind
- **存储**：本地文件系统 (MVP) → S3 (Phase 2)

## 模块

| 模块 | 职责 |
|---|---|
| M0 | 产品实体注册（CompetitorRegistry + DomainLexicon） |
| M1 | 场景网格管理（GridCell） |
| M2 | 映射卡（MappingCard，跨层契约） |
| M3 | 采集引擎（Adapter fan-out + 格子状态机） |
| M4 | 素材确认与标注（Observation + Claim） |
| M5 | 覆盖看板与搜索报告 |

## 快速启动

```bash
cp backend/.env.example backend/.env
docker-compose up -d postgres redis
cd backend && pip install -e ".[dev]"
uvicorn app.main:app --reload
cd ../frontend && npm install && npm run dev
```

## 文档

- [采集阶段完整方案 v2](docs/collection-phase-spec-v2.md)
