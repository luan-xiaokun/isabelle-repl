# TODO: add repair history (one theory)
# TODO: add agent memory -> from previous success/failure -> generalize / root cause

# Design of Proof Repair Agent

**Some goals in mind:**

- the main application scenario is to repair a broken proof after upgrading to a new version of Isabelle and relevant upstream libraries (e.g., Isabelle's standard library, AFP, etc.)
- use repair history to guide future repair attempts
- allow the agent to learn from past successes and failures to improve its repair strategies, possibly through a memory mechanism (e.g., generating a SKILL or some documentation)
- allow the agent to use our self-designed Isabelle tools (e.g., extracting dependencies of a fact in a specific Isabelle version; comparing the differences of two versions of a fact; inspecting proof states, theory files, context, etc.) to assist in the repair process
- allow the agent to apply sledgehammer to fix the proof, and use a boolean flag to control this policy
- a repair task should be iterative, meaning that the agent can launch multiple rounds of new commands to fix the script, and the agent can see the results of the previous round and decide whether to continue or not
- there should be a repair iteration budget, either per error/lemma or for the whole proof script
- to make the terminology consistent, we say:
    * a *repair task* is to fix a piece of broken block of proof script
        + a block block of proof script can be a terminating proof command (e.g., `by ...`), or a non-terminating proof command (e.g., `proof -`), or a whole proof for some declared proof (sub)goal, or the whole lemma (including its statement and its proof), or the whole non-lemma definition (e.g., `definition`, `fun`, `inductive`, etc.)
    * a repair task consists of multiple iterative *repair attempts*, and we say a repair task is successful if at least one of its repair attempts is successful, and we say a repair attempt is successful if the repaired proof script block can be accepted by Isabelle (i.e., the repaired proof script can be checked and verified by Isabelle)
        + here we introduce an assumption that, the repairing process would not change the proof script block too much, e.g., consistently replacing any broken block with `lemma trivial: "True" by simp` is not a successful repair. This could be an issue if the "fixed" proof is never consumed by any other theories (including itself). There seems no way to detect this issue, unless we prove that "the specification of the broken lemma in the previous version is equivalent to the specification of the repaired lemma in the new version", which is a highly non-trivial task.
    * a repair attempt is an interactive process launched by the agent. during a repair attempt, the agent first gathers initial information about the broken proof script block, e.g., the location of the failure in the theory file, the session name, the dependencies of the current theory files, preceding context in this file, the error messages, the proof state, etc. Then the agent can decide to collect more information, e.g., by calling tools to collecting dependencies in the previous version of Isabelle, or inspecting more theory files that it thinks might be relevant (like by searching or grepping); or the agent can directly generate a new command (or a whole proof script) to fix the broken part; or the agent could step back to some previous state; or the agent could fake a proof through `sorry` and continue to fix the remaining errors; or the agent could go back to the previous placeholder using `sorry` and continue to fix it.
    * a repair attempt consists of multiple steps of such actions, i.e., collecting information (usually by calling tools), generating new commands (including calling sledgehammer), stepping back to previous state (essentially undo some actions), temporarily faking proofs, going back to previous placeholders, and explicitly giving up.
    * there is a repair attempt step depth limit, which means that if the agent has taken more than a certain number of steps in a repair attempt, then the attempt is considered failed and terminated (if it gives up, also this case); if the agent successfully repairs the broken proof script, then the attempt is successful and terminated.
    * either a repair attempt is successful or failed, the agent could see the history / trace of this attempt. we could design a way to enforce the agent to learn from this history, e.g., by first inspecting the history and compare with its memory to see if there is any new information that it can learn; deciding whether to update the long-term memory that persists across different repair tasks, or just update the short-term memory that is only used for the current repair task; or generating a SKILL or some documentation to summarize the experience of this repair attempt, which can be used for future reference.

**Something to do with the current proof-repair script:**

- I still think it is quite useful, having some basic framework (though possibly not good enough), and importantly, those comments/TODO pointed out that, we actually need some mechanism to know when to skip and to know when we have finished a fix
- but I don't want to include it in the current python package, as it is less relevant
- at most, this script can be simplified and used as an example of how to use the repl tools

## What we want at this design stage

- a plan to modify the current repl package, i.e., dealing with the proof repair script
- a PRD about the "proof repair agent", which should clarify the boundary of this agent, its goals, and some important design decisions
- the PRD should be a tentative design, and we can iterate on it in the future, but it should be detailed enough to guide the prototyping and implementation of the proof repair agent, and it should also be clear enough to communicate with potential users or collaborators about what this agent is and what it can do.
