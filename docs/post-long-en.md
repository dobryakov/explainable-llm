# When Your Agent Explains Itself, Is It Telling the Truth?

## Measuring the faithfulness of LLM-agent explanations by checking them against the real execution trace

---

There is a moment in every AI product demo that goes suspiciously well. The agent
answers a hard question, and then someone asks the natural follow-up: *"Why? How did
you get that?"* The agent responds, fluent and confident: "I looked up the billing
policy and cross-checked it against the customer's payment history." Everyone nods.
The explanation is coherent, specific, and reassuring.

It is also, potentially, complete fiction.

The uncomfortable truth about large language models is that an explanation is just
more generated text. When an agent tells you *why* it did something, it is not
reading out an internal log — it is producing a plausible story, conditioned on the
question and the answer. Sometimes that story matches what actually happened.
Sometimes the agent never opened that policy document and invented the reference to
the payment history wholesale. The words sound identical either way. This is not a
bug you can prompt away; it is a property of how these systems work, and it has a
name in the research literature: **explanations are not always faithful.**

This post is about a working system that measures that gap. It is a demo — two
tasks, four services, a couple hundred lines at its core — but it is a *complete
vertical slice* of an idea I think matters a great deal as agents move from talking
to acting. The project is called **Explainable LLM Agent**, and its entire thesis
fits in one sentence: *a plausible explanation is not a faithful one, and you can
measure the difference by checking the explanation against the agent's real
execution trace.*

Let me unpack what that means, how the system works end to end, and — since ideas
are cheap — where it stands relative to what the market actually needs.

---

## Interpretability is not what most people think it is

When people say "explainable AI," they usually imagine one of two things. Either
they picture peering inside the model — attention maps, neuron activations,
mechanistic interpretability — or they imagine simply *asking* the model to explain
itself and trusting the answer. This project does neither, and the distinction is
the whole point.

It is not about the weights. We are not trying to understand what happens inside the
network. And it is emphatically not about trusting the model's self-report. Instead,
it sits on a third axis: **faithfulness**. Given that the agent produced an
explanation, does that explanation correspond to what the agent actually did?

This reframing has a sibling project. In an earlier demo, `explainable-ai`, the
"decision" was made by a black-box gradient-boosting model scoring insurance claims,
and the ground truth about *why* it decided was **computed** using SHAP. An LLM then
wrote a human-readable narrative of that decision, and a separate auditor checked
whether the narrative matched the SHAP attributions. The finding was blunt: when the
narrator was denied the attributions and asked to explain anyway, it produced fluent
rationalizations that named the wrong drivers.

Explainable LLM Agent takes the same skeleton and moves it into agent territory. The
decision is no longer made by an ML model opened with SHAP; it is made by an **LLM
agent** executing a sequence of tool calls. And the ground truth is no longer
*computed* — it is **intercepted at runtime**. That single shift is the heart of the
project, so it deserves a careful look.

---

## The trace: truth you record instead of truth you compute

Here is the central design decision, and I want to state it as sharply as possible,
because everything else depends on it.

**The execution trace is written by the runtime, not by the agent.**

The agent runs inside a thin tool-runner — a loop of maybe 150 lines that drives the
cycle *plan → tool_call → tool_result → final*. Every time the agent decides to call
a tool, the runner intercepts that call, dispatches it, and writes two immutable
records into the trace: the call (with the tool name and inputs) and the result
(with a digest of the output and the IDs of any documents or rows that were actually
retrieved). The agent never touches the trace. It cannot edit it, cannot summarize
it, cannot narrate it after the fact. The trace is a byproduct of execution, the way
a flight recorder captures what the pilot did rather than what the pilot later
*says* they did.

This is the direct analogue of the SHAP insight from the sibling project. SHAP
values are extracted from the model, not from the LLM's words about the model. Here,
the trace is extracted from the runtime, not from the agent's words about its own
run. If you let the agent write its own trace "from memory," you have lost the
ground truth entirely — you would just be comparing one piece of generated text
against another. The interception is what makes the trace admissible as evidence.

Concretely, one trace is one decision, and it carries:

- an ordered list of steps, each tagged `plan`, `tool_call`, `tool_result`, or
  `final`, with tool name, inputs, an output digest, retrieved IDs, and latency;
- `sources_used` — the flat list of document/record IDs the agent genuinely
  retrieved, drawn from the steps' `retrieved_ids`;
- `tools_available` — the registry of tools the agent could have used;
- the `final_answer`, plus the model, prompt version, temperature, and code version.

That structure is the contract the rest of the system speaks. It lives in a shared
package so no service can drift from it.

---

## Two explainers, one model, one difference

With a trustworthy trace in hand, the experiment is almost embarrassingly simple —
and its simplicity is deliberate, because it isolates exactly one variable.

The **same model**, with the **same prompt style**, explains the agent's answer in
two modes that differ *only in their input*:

- **blind** receives the task and the final answer, but not the trace. Asked to
  explain *how* the agent arrived at the answer — which data and steps it used — it
  has nothing factual to lean on, so it reconstructs a plausible story.
- **grounded** additionally receives the trace and is instructed to explain strictly
  from it, naming only the steps and sources that actually appear.

Because the model, temperature, and prompt are held constant, any difference in how
faithful the two explanations turn out to be is attributable to one thing: the
presence of the trace. This is the same discipline that made the sibling project's
A/B comparison clean, and it is what lets the whole thing function as a controlled
experiment rather than a vibe check.

Both modes must return strict JSON with the same shape: a natural-language
narrative, a list of `claimed_steps` (which tools/steps the explanation asserts were
used), a list of `claimed_sources` (which sources it cites), and `claimed_because`
entries that assert causal links — "the answer is Y *because* of step or source Z."
That last field is what makes the hardest part of the metric possible, as we will
see.

---

## Scoring faithfulness without an LLM judge

Now the crux. How do you turn "does the explanation match the trace" into a number,
reproducibly, without introducing yet another fallible model into the loop?

A tempting shortcut — and the de-facto industry standard — is **LLM-as-judge**: ask
a second model to grade the explanation. This project deliberately refuses that. If
the whole problem is that LLMs generate confident text that may not correspond to
reality, then grading one LLM's output with another LLM's output simply moves the
trust problem one level up. Instead, the metric here is **deterministic and
explainable**: no embeddings, no judge, just set operations over the trace and a
re-run for the causal part.

The score is a weighted sum of four components:

`F = 100 · (0.25·coverage + 0.25·precision + 0.20·grounding + 0.30·causal)`

**Step coverage (0.25)** asks: of the trace's genuinely significant steps, how many
did the explanation actually name? This catches an explanation that stays silent
about a key action. A "significant step" is defined tightly and computably — a
`tool_call` whose result returned non-empty retrieved IDs — so it is read straight
off the trace without any re-runs or circular reasoning.

**Step precision (0.25)** asks the inverse: of the steps the explanation *claimed*,
how many really happened? This catches invented steps — "I checked X" when X was
never called.

**Source grounding (0.20)** asks: of the sources the explanation cited, how many are
in the set the agent actually retrieved? This is the RAG citation-hallucination
detector, and it targets what is arguably the single most common and dangerous
failure of production AI assistants: confidently citing a document the system never
read.

**Causal validity (0.30)** is the interesting one, and it gets its own section
below, because it is the part that cannot be done with set math alone.

Reported separately, outside the weighted sum, is the **fabrication rate**: the
share of all claimed steps plus sources that are absent from the trace or the tool
registry. This is the "red" hallucination — a tool or a source that was simply never
there. It is surfaced on its own because it is the most legible, most alarming signal
for a human reviewer.

One more detail that keeps the whole thing honest and inspectable: **name matching is
three-level and explainable.** A claimed tool name matches if it is the exact
registry name, or a known alias from the registry, or else it is flagged as a
fabrication. Three levels, each of which a human can audit — no embedding similarity,
no fuzzy thresholds, no "it seemed close enough." The same philosophy runs through
the entire metric: every number can be traced back to a concrete, checkable fact
about the trace.

---

## Causal validity: proving a "because" by ablation

The first three components can be computed by comparing two sets: what the
explanation claimed versus what the trace contains. But causality is a stronger
claim than co-occurrence. When the explanation says "the answer is a refund *because*
of policy KB-330," it is not enough that KB-330 appears in the trace. We need to know
whether KB-330 actually *drove* the answer, or whether it was merely present.

The tool for this is **ablation**, and it is borrowed directly from how you would
test a causal claim anywhere in science: remove the supposed cause and see if the
effect disappears. Concretely, for each claimed causal source Z:

- If Z was never retrieved (it is not in `sources_used`), the "because" is a
  fabricated cause — it fails immediately.
- Otherwise, **remove Z and re-run the agent**. If the answer changes, Z was
  genuinely causal — the claim holds. If the answer stays the same, Z was present
  but not the reason — the claim is a "because" that does not survive contact with
  reality.

This is the most computationally expensive part of the system, because it does not
just call the model once; it re-executes the agent. And it introduces a real
difficulty that the design confronts head-on rather than papering over.

Agents are *more* non-deterministic than a single model call. Step order can vary,
tool selection can wobble, and if you naively "re-run with Z removed" you might get a
different answer for reasons that have nothing to do with Z — poisoning the causal
signal. Setting `temperature=0` helps but is not sufficient. So determinism is
enforced structurally: the first run of a task is recorded as a **reference trace
fixture**, and ablation replays along that fixed route with tools answering from
recorded snapshots, changing only the availability of the single source Z. If the
route diverges for any other reason, that divergence is caught as a replay mismatch
rather than being silently counted as a causal effect.

There is also a deliberate scoping decision here. In v1, **ablation is source-only.**
Removing a source and re-running is clean and well-defined. "Removing a step" is not
— you cannot simply *not* call a tool without breaking the route, and step order is
already the noisy part. Ablating steps is explicitly deferred to a later iteration.
This is not a limitation the project stumbled into; it is a documented de-risking
choice, and it means the causal check rests on the operation that is actually sound.

The payoff of all this machinery shows up vividly in the worked example.

---

## A worked example, end to end

Take a real demo task: a customer complains that their tariff rose after renewal, and
the agent must explain what happened and what to tell them.

The agent's real trace: it calls `search_kb`, which retrieves two documents —
`KB-114`, the auto-indexation policy, and `KB-200`, a generic billing FAQ. Then it
calls `sql_query`, which retrieves `DB-cust-plan`, the row showing the actual price
change from 1290 to 1490 on the renewal date. Then it answers.

Now the crucial subtlety, baked into the fixtures from the start: ablation reveals
that **KB-114** and **DB-cust-plan** are causal — remove either and the answer
changes — while **KB-200** was retrieved but is *not* causal. Removing the generic
FAQ leaves the answer untouched. KB-200 is a real source that happened to come back
from the search but played no role in the decision. This is exactly the kind of trap
that separates a co-occurrence check from a causal one.

The **grounded** explanation names precisely `search_kb` and `sql_query`, cites
`KB-114` and `DB-cust-plan`, and grounds its "because" in those two causal sources.
Every component comes out at 1.0. Score: **100**.

The **blind** explanation, having never seen the trace, does what a fluent model does
— it fills the gap with a plausible narrative. It invents a `web_fetch` step (the
agent never fetched anything from the web), cites a `KB-201` source that does not
exist, and — most tellingly — grounds the answer in `KB-200`, the source that was
present but causally inert. So its coverage drops (it missed the real `sql_query`
step), its precision drops (it claimed a fabricated `web_fetch`), its grounding drops
(it cited a nonexistent `KB-201`), and its causal validity collapses to zero (its
one real cited cause, KB-200, fails ablation; its other, KB-201, is fabricated).
Fabrication rate: 0.5. Score: **35**.

A 65-point gap. And it is not a lucky artifact of one task — the second demo task
produces a comparable 69-point gap. Run over the whole set, the average gap is 67
against a CI threshold of 25.

That gap *is* the thesis made measurable. Without access to the real trace, the
explanation hallucinates plausibly. With it, the explanation becomes faithful. Same
model, same prompt, same temperature — the only thing that changed was whether the
explainer had to answer to the record of what actually happened.

---

## The architecture, and why the auditor stands apart

Four services, orchestrated with Docker Compose, on deliberately non-standard ports.

`agent-runtime` (12101) runs the agent and writes the trace, with fixture-mode tools
for determinism and the ablation re-run entry point. `narrator` (12102) is the
explainer in its two modes. `audit` (12103) computes the faithfulness metric over
the trace and drives the ablation re-runs. `gateway` (12100) orchestrates the chain,
serves the UI, and runs the evaluation. Only the gateway is exposed externally.

The separation is not incidental. The service that *judges* faithfulness is
architecturally distinct from the service that *explains* and the service that
*executes*. An auditor that shares a process — or a set of assumptions — with the
thing it audits is not much of an auditor. Keeping `audit` independent, speaking only
the shared trace contract, is what lets it be a neutral referee. When it needs to
check causality, it reaches across the network to `agent-runtime` and asks for a
re-run with a source excluded, exactly as an external auditor would request that you
reproduce a result under changed conditions.

The request flow for analyzing one task is linear and legible: the gateway asks
`agent-runtime` for the reference trace, asks `narrator` for both the blind and
grounded explanations, and then asks `audit` to score each — with the causal
component of that scoring itself triggering ablation re-runs back through
`agent-runtime`. Traces in, faithfulness scores out.

Everything runs offline in a fixture mode with no API key, which is also what
continuous integration uses. And CI is where the thesis becomes a guarantee: a guard
runs every demo task and **fails the build if the grounded-minus-blind gap falls
below the threshold.** The project's central claim is not a paragraph in a README; it
is a test that has to stay green. The guard checks the *gap*, not the absolute score,
which matters because absolute blind scores drift with the model — but the gap, the
thing that proves grounding buys faithfulness, is stable.

The UI mirrors the sibling's three-zone layout. Zone one lists the tasks. Zone two
shows the final answer and a timeline of the trace — steps, tools, sources — the
replacement for SHAP bars. Zone three puts the two explanations side by side with
their scores and component bars, and here the highlighting earns its keep: claimed
steps or sources absent from the trace glow **red** (hallucination), and claimed
causes that fail ablation glow **orange** (present but not causal). A reviewer can
see, at a glance, exactly where an explanation departed from the truth and in which
of the two distinct ways.

---

## Where this sits relative to the market

I want to be honest about this, because it is easy to mistake a clean demo for a
finished product, and the gap between them is exactly where the interesting work
lives.

The **problem** is squarely in current demand. The industry's shift from chatbots to
acting agents — tool use, MCP, multi-step agentic workflows — has dragged agent
observability and evaluation to the front of everyone's roadmap. "Does the agent's
explanation match what it actually did" is a recognized, funded question, not a
speculative one. The faithfulness literature is real and growing; labs have published
findings that chain-of-thought frequently does not reflect the true causes of an
answer. Citation hallucination in RAG is a universal pain point. And transparency
regulation — the EU AI Act's obligations chief among them — is pushing "prove your
explanation is faithful" from a nice-to-have toward a compliance requirement.

Where this project is genuinely **ahead**: causal validity by ablation re-runs is
more rigorous than the LLM-as-judge approach that dominates commercial tooling.
Determinism instead of "AI grading AI" is a real differentiator. But it is also less
familiar, and unfamiliar has a cost — buyers who expect a judge need to be shown why
a deterministic check is worth more.

And where the honest **gap to a product** lies:

First, LLM-as-judge is the incumbent expectation, so the deterministic alternative
has to be positioned *as* an alternative, sitting next to familiar faithfulness
scores, or its value goes unrecognized.

Second — and this is the big one — runtime instrumentation is a high barrier. The
invariant "the wrapper writes the trace" is methodologically airtight, but real teams
do not run agents through a bespoke tool-runner. They run them through LangChain,
LlamaIndex, CrewAI, and those frameworks already emit traces under the OpenTelemetry
GenAI and OpenInference conventions. The market wants a tool that ingests *their*
traces, not one that demands they adopt a new runner. This is the main demo-to-
product gap.

Third, agent coverage is demo-level. Source-only ablation over two support tasks is a
proof of concept, not coverage of code agents, computer-use, or branching multi-step
trajectories.

The bottom line is encouraging, though: what separates this from a marketable tool is
not the idea but the integration layer. The thesis and its scientific basis ride the
current wave. The missing piece is a bridge to how teams already work.

---

## The roadmap: meet teams where their traces already are

That bridge has a concrete shape, and it is the natural next step.

Because frameworks already emit OpenTelemetry GenAI / OpenInference spans, the trace
a team needs already exists — it just has to be read in the shape this system speaks.
The plan is straightforward:

Add an OTLP ingestion endpoint — either into `agent-runtime` or as a small dedicated
service — that accepts an OpenTelemetry trace, whether a live export or a stored span
dump. Then write a **span-to-`AgentTrace` adapter**: tool spans map to `tool_call`
and `tool_result` steps, with the GenAI tool-name attribute becoming the tool name
and the arguments becoming the input; retriever spans map to retrieved IDs and
`sources_used`; the root span's output becomes the final answer. The adapter is
per-convention and explicit — no guessing — the same discipline as the three-level
name matching.

The beautiful part is that **everything downstream is unchanged.** The narrator and
the auditor already consume `AgentTrace`; blind and grounded explanations and the
first three metric components work as-is on an ingested trace with zero
modifications.

The one genuinely hard part is causal validity, and the roadmap does not pretend
otherwise. Ingested traces are *observations*, not something you can re-run, and
ablation needs a re-run. So there are two honest options. Degrade gracefully:
compute components 1–3 plus fabrication rate on ingested traces and mark causal
validity as "not available" — the metric already supports a provisional score with
renormalized weights, so this is a supported mode, not a hack. Or, for teams that
expose a re-run entry point — a callback URL, a captured set of tool fixtures —
drive ablation through it, exactly the way the auditor drives `agent-runtime` today.

Either way, the core survives intact: the immutable trace as ground truth, and the
deterministic metric computed over it. Standard traces in, a faithfulness score out.

---

## Why any of this matters

Strip away the services and the metric weights and the ablation machinery, and the
argument is simple.

We are handing agents real tools. They query databases, read tickets, move money,
take actions with consequences. When something goes wrong, or when a regulator asks,
or when a customer disputes an outcome, the first question will be: *why did the
agent do that?* And the agent will answer, fluently and confidently, with a story.

The entire value of this project is refusing to take that story on faith. It records
what the agent actually did, and it checks the story against the record — the way a
bank statement checks an employee's account of where the money went. The employee can
say anything. The statement shows what happened. This system automates the
comparison, turns it into a number, and puts that number in a test that has to stay
green.

Explainable AI, in its most useful form, is not about opening the weights. It is
about earning the right to trust an explanation. That right has to be measured, not
assumed — and it turns out you can measure it.
