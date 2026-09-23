# ADR-0006 — Curated corpus + Ragas eval on LangSmith

Status: accepted.

Context: No single trusted "family law" dump; random Kaggle data risks wrong jurisdiction; verified-answers claim needs proof.

Decision: Corpus = `vaquill/open-india-law` filtered to 6 family acts + `enerscript/MARRIAGEACT` + India Code PDFs + 20–30 curated judgments. Eval = 30 golden Q&As (10/lang, seeded from `steamed-potatop/indian-family-law-data`), Ragas faithfulness + relevancy + context recall, tracked in LangSmith. Langfuse dropped — LangSmith alone is enough for solo.

Consequences: Manual curation + golden-set writing up front; every retrieval change re-runs eval.
