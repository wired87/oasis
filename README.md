# Oasis

## What Is Oasis?

Oasis is a human-centered AI ecosystem that turns personal knowledge and real-life data into real economic value.  
Think of it as a platform where your data is no longer just consumed by faceless corporations — instead, it actively works **for you**, generating income every time it is used.

---

## The Problem It Solves

Most AI systems today are trained on your data without giving you anything back.  
Oasis flips this model: **you own your data, you share it on your terms, and you get paid when it creates value**.

---

## How It Works — Step by Step

```
User shares data  →  AI model processes it  →  Result is rated  →  Coin value increases  →  User gets paid
```

1. **You contribute your data** — searches, preferences, lived experience, project results, or any structured dataset you choose to share.
2. **The AI (Brain layer) accesses your data** to generate meaningful outputs: answers, summaries, project packages, or actionable insights.
3. **Every access is rated** — each time the model reads one of your datasets, an automated rating system calculates the quality and usefulness of that data.
4. **That rating creates coin value** — the rating directly influences the value of the ISYS coin on the blockchain. More useful data → higher rating → higher coin value.
5. **You earn from successful outcomes** — contributors are rewarded in ISYS coin when their data drives a successful AI execution (e.g., a completed project, a delivered recommendation, a finished workflow).

---

## The Business Model

Oasis is built on a **data-value loop**:

- **Contributors** (users who share datasets) sign a smart contract when they join. This contract defines their share of the value their data generates.
- **Every successful AI execution** — powered by COR (a companion project that orchestrates automated AI workflows) or other projects in the ecosystem — flows value back through the network like electricity through a wire.
- **Electricity analogy**: just as electricity flowing through a circuit powers devices, every successful transaction "flows" through the network and increases the volume and value of the underlying coin.
- **The coin value rises** with activity: more successful executions → more demand for the coin → higher price → higher payout for contributors.
- **Smart contracts automate fairness** — no manual invoicing, no middlemen. The contract you sign at onboarding governs every future payout automatically.

---

## Key Components

All files listed below are present in this repository:

| Component | Role |
|-----------|------|
| `brain.py` | Central AI processing layer — listens, retrieves, and produces results |
| `data.py` | Ingests and ranks user datasets; feeds the rating system |
| `blockchain.py` | Manages the ISYS coin, registers contributors, and executes smart contracts |
| `ledger.py` | Tracks individual balances, deposits, and payouts per user |
| `mcp_master.py` | Master control process — orchestrates multi-step AI workflows |
| `yt.py` | YouTube data integration — one example of a real-life data source |

---

## Simple Workflow

```
User → Brain (AI processing + retrieval) → Rated output → Blockchain payout → User wallet
```

The Brain layer listens, organizes what matters, produces direct and useful results, and triggers an on-chain reward when a task completes successfully.

---

## Human Value

When people can share their real experience and knowledge, they contribute to something larger than themselves — and they get rewarded for it.  
Oasis is not just a platform; it is an economic engine that recognizes **your data as your most valuable asset**.

---

## Intelligent Web Direction

Instead of browsing one website at a time, users receive complete knowledge blocks — ready-to-use bundles of answers, context, and next steps — or even full project packages, all in one flow.  
This reduces friction and maximizes productivity for both technical and non-technical users.

---

## Getting Started

Clone the repository and run the Brain entry point:

```bash
python brain.py
```

Run with Docker:

```bash
docker build -t oasis . && docker run --rm oasis
```

---

## License

See [LICENSE](LICENSE) for details.
