# Hired Hands

Three robot arms that sell their work by the job and settle every job on the XRP Ledger.

Anyone, including another program, can hire the cell with a single HTTP request. The request is answered
with `402 Payment Required`; the hirer pays in XRP, the cell verifies and settles the payment itself, and
the job runs. A camera arm reads the table, the two working arms bid for the job, the winner's pay is
locked in an escrow that only the camera arm can release, the work is done and checked, and the money
moves in one atomic batch. When the arms cannot finish, a person takes the controls and is paid by the
second over a payment channel. The arms borrow from a lending vault to fund themselves and repay from
what they earn, and each carries a live health credential that is revoked the moment a servo stops
answering.

The live dashboard at [hiredhands.vercel.app](https://hiredhands.vercel.app) shows all of it as it happens.

## Layout

| Path | What it is |
|---|---|
| `cell/` | The workcell daemon (Python): arm drivers, perception, skills, the job pipeline, the ledger client and the job API |
| `web/` | The dashboard (Next.js), deployed on Vercel |
| `supabase/` | The schema the cell writes to and the dashboard reads from |

## How a job runs

1. **Hire.** `POST /jobs` with an instruction such as `put the red block in the blue cup`. The response is a 402 carrying x402 payment requirements; an x402 client retries with a presigned XRP payment and receives the job.
2. **Look.** The head arm takes its survey pose. Four printed markers fix the table frame; every object on the sheet becomes a numbered candidate with table coordinates.
3. **Decide.** A vision-language model, or the colour words in the instruction, picks the target and the destination among the numbered candidates.
4. **Bid.** Each working arm quotes a price from its reach, its distance to the work, its health and its debt. The lowest feasible bid wins.
5. **Lock.** The treasury escrows the winning bid for the winner behind a crypto-condition. The head arm holds the secret.
6. **Work.** The winner picks and places with inverse kinematics on the shared table frame, or the arms play a recorded skill that matches the instruction.
7. **Check.** The head arm looks again. If the target ended where it was asked to go, the head releases the escrow.
8. **Settle.** One all-or-nothing batch pays the head's verification fee, the operator's fee and, when the worker has a loan, its repayment.
9. **Hand over.** If a step fails, a person can drive the arm from the keyboard; every second is signed over a payment channel and redeemed when they hand the arm back.

## Ledger

Everything runs on the XRP Ledger Devnet: conditional escrows, payment channels, credentials, a permissioned domain, decentralised identifiers, batch transactions, a single-asset vault and the lending protocol. The job API speaks x402 and the cell runs its own facilitator.

## Running the cell

Requirements: Python 3.12, [lerobot](https://github.com/huggingface/lerobot), three SO-101 arms on USB, a UVC camera on the head arm's wrist, and the printed work surface.

```bash
pip install -e cell
cp cell/.env.example cell/.env      # fill in the database key and, optionally, a model key
hands setup                         # fund the cell's accounts, publish the arms' identities
hands board                         # print cell/captures/work-surface.png at 100 % scale
hands pose head head.survey         # the viewpoint over the table
hands calibrate                     # the arms measure the camera and each other; no printed target needed
hands serve                         # the cell and its API
```

Hire it:

```bash
hands hire "put the red block in the blue cup"
```

`hands serve --tunnel --voice --teleop` also opens a public address, a voice front desk on the dashboard, and the keyboard takeover for a human operator.

Recorded skills: record one take per arm with any teleop that writes joint frames, then

```bash
hands take import drone ./recordings --instruction "put the white drone in the orange container"
hands take play drone
```

## Dashboard

Deployed at [hiredhands.vercel.app](https://hiredhands.vercel.app). To run it locally:

```bash
cd web && pnpm install && pnpm dev
```

Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_KEY` to the project the cell writes to.

## License

MIT
