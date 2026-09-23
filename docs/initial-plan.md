# 1. Project Title

### **LawSaathi – Multilingual Agentic AI-based Legal Support System**

**Focus:** Family Law

The system is designed as an **intelligent legal assistant** that helps users understand family-law-related information, rights, duties, procedures, case laws, and legal documents.

The important part is that it isn't presented as just a normal chatbot.

It is designed as an **Agentic AI system**, meaning the AI can:

> Understand → Plan → Retrieve → Use Tools → Reason → Verify → Respond

rather than simply generating an answer from its pretrained knowledge.

The system supports:

* English
* Hindi
* Kannada
* Text interaction
* Voice interaction
* Legal-document understanding
* Legal information retrieval
* Case-law search
* Step-by-step guidance
* Conversation memory

---

# 2. Problem Statement

The problem identified in the project is that **ordinary people struggle to understand complex family laws and find current, reliable legal information in their own language**. Existing legal search systems are described as largely English-oriented, text-based, and not conversational. 

The project identifies **six major problems**.

### 2.1 Complex Legal Language

Legal documents contain:

* Legal terminology
* Acts
* Sections
* Judgments
* Court language
* Formal procedures

A normal person may not understand these documents.

For example, instead of simply saying:

> "You can file for divorce..."

a legal document might describe the applicable statute, section, grounds, jurisdiction, procedural requirements, etc.

LawSaathi aims to translate this complexity into **simple language**.

---

### 2.2 Language Barrier

A large amount of legal information is available in English.

But users may be more comfortable asking questions in:

* Hindi
* Kannada
* English

The system therefore provides **multilingual interaction**.

For example:

> User: "ನನಗೆ ವಿಚ್ಛೇದನ ಪಡೆಯಲು ಏನು ಮಾಡಬೇಕು?"

The system should understand the user's intent and provide the response in the appropriate language.

---

### 2.3 Outdated or Irrelevant Information

Legal information can change.

There may be:

* New judgments
* Amendments
* Notifications
* Changes in rules
* New interpretations

A system that relies only on its pretrained LLM knowledge can potentially provide outdated information.

Therefore, the project includes **real-time web search** and retrieval from trusted sources.

---

### 2.4 Information Overload

Searching the internet for a legal question can return:

* Blogs
* Articles
* Old judgments
* News
* Unverified websites
* Irrelevant documents

The user then has to determine what information is trustworthy.

LawSaathi introduces a retrieval and filtering process to find **relevant legal information**.

---

### 2.5 Lack of Clarification and Guidance

Traditional search engines generally return documents.

They don't necessarily ask:

> "Which type of divorce are you referring to?"

or:

> "Are you asking about maintenance or child custody?"

LawSaathi's agentic workflow can detect when additional information is required and **ask clarifying questions** before generating the answer.

---

### 2.6 Limited Voice Support

The project also identifies limited conversational voice interaction in existing systems.

LawSaathi therefore includes:

* Speech-to-text
* Voice processing
* Text-to-speech
* Real-time voice interaction

These challenges are explicitly listed in the problem-statement slide. 

---

# 3. Proposed Solution – LawSaathi

The proposed solution is **LawSaathi**, a multilingual Agentic AI legal assistant specifically focused on **Family Law**.

The system combines:

### **Agentic AI + RAG + Real-Time Voice Interaction**

The goal is to make legal information:

* Accessible
* Understandable
* Context-aware
* Actionable
* Multilingual

The system is designed to help users understand:

* Rights
* Duties
* Legal procedures
* Case laws
* Judgments
* Documents
* Next steps

The solution architecture and agent workflow are described across pages 3, 5, 6, and 7 of the document.  

---

# 4. What Does "Agentic AI" Mean Here?

This is one of the **most important concepts for your viva**.

A normal chatbot can work like:

```text
User
 ↓
LLM
 ↓
Answer
```

LawSaathi is designed more like:

```text
User
 ↓
Understand Intent
 ↓
Plan
 ↓
Retrieve Information
 ↓
Use Tools
 ↓
Reason
 ↓
Verify
 ↓
Generate Response
 ↓
Ask Clarification / Give Next Steps
```

The project describes multiple specialized agents.

### Agents shown in the project:

1. **Intent / Understanding Agent**
2. **Planner Agent**
3. **Tool-Using Agent**
4. **Verifier Agent**
5. **Response Agent**

There is also **shared memory/context** between the agents. 

---

# 5. Agent 1 – Intent / Understanding Agent

The first agent determines:

> "What exactly is the user asking?"

It identifies things such as:

* User intent
* Legal topic
* Entities
* Case type
* Relevant parties
* Other important information

For example:

### User asks:

> "Can I get child custody after divorce?"

The intent agent could identify:

```text
Intent = Child custody information
Domain = Family Law
Context = Divorce
Entity = Child custody
```

The system can then pass this structured understanding to the next agent.

---

# 6. Agent 2 – Planner Agent

The Planner Agent decides **how to solve the user's question**.

Instead of directly answering, it creates a plan.

For example:

```text
Question:
"What are my rights regarding maintenance after divorce?"

Planner:

1. Identify applicable family-law provisions
2. Search legal knowledge base
3. Search recent legal sources
4. Retrieve relevant judgments
5. Compare retrieved evidence
6. Ask clarification if necessary
7. Generate answer
8. Verify answer
```

This is a major difference between a basic chatbot and an **agentic system**.

The project architecture specifically shows the planner deciding actions and coordinating retrieval/search/document analysis. 

---

# 7. Agent 3 – Tool-Using Agent

The Tool-Using Agent actually interacts with external tools.

The project mentions tools such as:

### RAG search

Searches the internal legal knowledge base.

### Web search

Uses **Firecrawl** for web search/data extraction.

### Document analysis

Processes uploaded legal documents.

### Retrieval

Retrieves relevant legal documents and information.

### External APIs

The project also identifies external sources such as:

* Courts
* Bare Acts
* Government sources

as potential external legal sources. 

---

# 8. Agent 4 – Verifier Agent

This is another important component.

The Verifier Agent checks the generated/retrieved information for things such as:

* Accuracy
* Consistency
* Relevance
* Citations
* Reliability

The architecture contains a **VERIFY** stage.

If the evidence is insufficient, the workflow can go back and retrieve additional information rather than immediately returning an answer. 

This is intended to reduce the risk of hallucinated legal information.

---

# 9. Agent 5 – Response Agent

Once the information has been verified, the Response Agent produces the final answer.

The response should be:

* Clear
* Accurate
* Context-aware
* In the user's language
* Supported by citations
* Action-oriented

It can provide:

### Legal explanation

Explain the law in simple language.

### Case laws

Provide relevant judgments.

### Step-by-step guidance

Explain what the user can do next.

### Disclaimers

Indicate limitations and the need for professional legal advice where appropriate.

---

# 10. RAG – Retrieval Augmented Generation

**RAG is one of the core technologies of LawSaathi.**

RAG stands for:

> **Retrieval-Augmented Generation**

Instead of asking the LLM to answer only from its pretrained knowledge, the system first retrieves relevant information.

### Without RAG:

```text
User Question
      ↓
LLM
      ↓
Answer
```

### With RAG:

```text
User Question
      ↓
Query Understanding
      ↓
Search Legal Knowledge
      ↓
Retrieve Relevant Documents
      ↓
LLM
      ↓
Grounded Answer
```

The project's architecture includes a **Legal RAG** component using **Qdrant + embeddings**. 

---

# 11. Vector Database – Qdrant

The project uses:

### **Qdrant**

as its vector database.

Its purpose is:

* Store vector embeddings
* Perform similarity search
* Retrieve semantically relevant legal information

Suppose the database contains:

> "Section X discusses maintenance rights..."

The user asks:

> "Can a wife claim financial support after separation?"

The exact words may not match.

But vector similarity can recognize that the concepts are related.

---

# 12. Embeddings (decided: `intfloat/multilingual-e5-small`)

> Update (grill-with-docs): the initial suggestion `all-MiniLM-L6-v2` was
> replaced. MiniLM is English-only and fails Hindi/Kannada retrieval.
> Decided model: **intfloat/multilingual-e5-small** — small, free to run
> locally via Sentence Transformers, covers EN + HI + KN. See ADR-0003.

The project uses Sentence Transformers for text embeddings. 

An embedding converts text into a numerical vector.

For example:

```text
"child custody after divorce"
             ↓
       [0.12, -0.42, 0.81, ...]
```

Another semantically similar sentence will have a nearby vector.

Qdrant can then search for the closest vectors.

---

# 13. Real-Time Web Search – Firecrawl

The project uses:

### **Firecrawl**

for:

* Real-time web search
* Data extraction
* Document/web content retrieval

This is important because legal information can change.

The system can combine:

```text
Internal Legal Knowledge
        +
Real-Time Web Search
        ↓
Relevant Evidence
        ↓
Legal Reasoning
```

Firecrawl appears in both the tech stack and workflow architecture. 

---

# 14. Document Ingestion and Q&A

One of the proposed features is:

### **Document Ingestion & Q&A**

The user can upload a legal document and ask questions about it.

For example:

> Upload: Divorce petition / judgment

Then:

> "What does this document say about child custody?"

The system can extract the document's content and answer questions based on it.

The feature is explicitly listed on the Features page. 

---

# 15. Multilingual Chat

LawSaathi supports:

### English

### Hindi

### Kannada

The user can communicate in their preferred language.

For example:

```text
English:
"What are my rights after divorce?"

Hindi:
"तलाक के बाद मेरे क्या अधिकार हैं?"

Kannada:
"ವಿಚ್ಛೇದನದ ನಂತರ ನನ್ನ ಹಕ್ಕುಗಳೇನು?"
```

The system should understand the intent and provide the response appropriately.

The project specifically identifies multilingual chat as a decided feature. 

---

# 16. Voice Interaction

Another major feature is **voice interaction**.

The tech stack mentions:

### Sarvam AI

for:

* STT — Speech-to-Text
* TTS — Text-to-Speech

The architecture additionally shows:

### LiveKit

for real-time voice agents and communication. 

So the flow can be:

```text
User speaks
     ↓
Speech-to-Text
     ↓
LawSaathi Agent
     ↓
Legal Retrieval + Reasoning
     ↓
Answer
     ↓
Text-to-Speech
     ↓
User hears response
```

---

# 17. Case Law & Precedent Search

The system includes:

### **Case Law & Precedent Search**

This allows users to find relevant:

* Judgments
* Case laws
* Precedents

The project says this should provide relevant judgments with citations. 

For example:

> "Are there previous cases related to child custody in similar circumstances?"

The system can search its available legal sources and retrieve relevant cases.

---

# 18. Legal Information Retrieval

Another explicit feature is:

### Legal Information Retrieval

It is intended to retrieve information from:

* Acts
* Rules
* Notifications
* Legal databases
* Other legal sources

The project describes this as **real-time search across relevant legal sources**. 

---

# 19. Step-by-Step Legal Guidance

Instead of simply returning a definition, LawSaathi is intended to give:

> **What should I do next?**

For example, conceptually:

```text
Step 1 → Identify applicable legal issue
Step 2 → Collect required documents
Step 3 → Identify relevant authority/court
Step 4 → Understand applicable procedure
Step 5 → Consider next legal step
```

The project specifically calls this **Step-by-Step Guidance**. 

---

# 20. Chat History

The system includes:

### Conversation History

This allows previous interactions to be maintained.

For example:

### Conversation 1

User:

> "What is maintenance?"

Later:

> "How do I apply for it?"

The system can use the earlier conversation as context.

---

# 21. Memory

The architecture describes:

### Short-Term + Long-Term Memory

The Memory Manager stores relevant context such as:

* Conversation context
* User preferences
* Retrieved knowledge
* Session information

The purpose is to provide continuity across interactions. 

---

# 22. User Preferences

The Features slide specifically includes:

### User Preferences

The system can remember preferences such as:

* Preferred language
* Tone
* Response style

For example, a user could prefer:

> Kannada + simple explanation

Future responses can take that preference into account. 

---

# 23. Verified & Safe Responses

This is particularly important because the application is dealing with **legal information**.

The project proposes:

* Citation-backed answers
* Verification
* Confidence considerations
* Disclaimers

The system should avoid presenting uncertain information as absolute legal advice.

The Features page explicitly describes **Verified & Safe Responses**. 

---

# 24. Legal Document Support

The system is designed to help users:

* Search documents
* Extract information
* Understand documents
* Ask questions about documents
* Retrieve relevant content

This makes the system more than a question-answer chatbot.

---

# 25. Complete Technology Stack

Now let's break down **every technology shown in the PDF**.

The tech-stack page describes the system as a modern, scalable stack for multilingual legal assistance with text and voice support. 

---

## Frontend

### **Next.js**

Hosted/deployed through:

### **Vercel**

The frontend is the user-facing web application.

It provides:

* Chat UI
* User interaction
* Voice interface
* Document upload
* Conversation history
* Multilingual interface

---

# 26. Backend

### Python

The core backend/business logic is implemented using Python.

### FastAPI

FastAPI acts as the backend API framework.

It handles:

* API requests
* Request processing
* Authentication
* Validation
* Rate limiting
* Logging

The architecture explicitly shows FastAPI as the **API Gateway & Request Handler**. 

---

# 27. Agent Framework – LangGraph

### **LangGraph**

This is arguably one of the most important technologies in the project.

It handles:

* Agent orchestration
* Workflows
* Tools
* Memory
* Agent coordination

Instead of writing one giant AI function, you can represent the system as a graph:

```text
START
 ↓
Intent Agent
 ↓
Planner
 ↓
Tool Agent
 ↓
Verifier
 ↓
Response Agent
 ↓
END
```

And the workflow can loop when more information is needed.

---

# 28. LLM – Groq / OpenRouter

The project identifies:

### Groq

as the primary LLM access/provider.

### OpenRouter

as a fallback/backup model access mechanism.

The LLM is responsible for tasks such as:

* Understanding natural language
* Reasoning
* Planning
* Summarization
* Generating responses
* Legal-context reasoning

The project architecture explicitly shows Groq as primary and OpenRouter as fallback/backup. 

---

# 29. PostgreSQL – Neon

The project uses:

### **Neon PostgreSQL**

for relational data.

The architecture lists it for:

* Metadata
* Users
* Sessions
* Logs
* Conversation information

So conceptually:

```text
Qdrant → semantic/vector search

Neon PostgreSQL → structured application data
```

The tech-stack and architecture pages both identify Neon PostgreSQL. 

---

# 30. Qdrant vs Neon

This is a good viva question.

### Qdrant

Used for:

> **Vector / semantic search**

Example:

```text
"divorce maintenance rights"
```

Finds semantically similar legal documents.

### Neon PostgreSQL

Used for:

> **Structured relational data**

Example:

```text
User
Session
Conversation
Metadata
Logs
```

So:

| Qdrant          | Neon                |
| --------------- | ------------------- |
| Vector database | Relational database |
| Semantic search | Structured data     |
| Embeddings      | Metadata            |
| Legal retrieval | Users/sessions/logs |

---

# 31. Firecrawl

Firecrawl is included for:

### Web Search + Data Extraction

It allows the agent to retrieve relevant web information and extract usable content.

This becomes one of the tools available to the Tool-Using Agent.

---

# 32. Sarvam AI

Sarvam is used for:

### STT

Speech → Text

and

### TTS

Text → Speech

This is what enables multilingual voice interaction.

---

# 33. LiveKit

LiveKit is shown under the Voice & Communication Layer.

It is intended for:

* Real-time voice agents
* Real-time communication

So Sarvam handles speech capabilities while LiveKit supports the real-time communication layer. 

---

# 34. LangSmith

### LangSmith

is used for:

* Tracing
* Debugging
* Monitoring agent workflows

This is useful because Agentic AI can involve multiple steps.

For example:

```text
User
 ↓
Intent Agent
 ↓
Planner
 ↓
Qdrant
 ↓
Firecrawl
 ↓
LLM
 ↓
Verifier
 ↓
Response
```

If the answer is incorrect, LangSmith-style tracing helps determine **where the workflow went wrong**.

---

# 35. Langfuse

### Langfuse

is listed under:

### Observability & Analytics

It can be used for monitoring AI application behavior and analyzing LLM/agent interactions.

The architecture groups it with tracing, observability, performance, errors, and audit logs. 

---

# 36. Deployment

The project lists:

### Vercel

for frontend hosting.

### Render

for backend hosting.

So the deployment architecture is approximately:

```text
                    USER
                      |
                      v
              Vercel / Next.js
                      |
                      v
                FastAPI Backend
                      |
                      v
                LangGraph
               /    |     \
              /     |      \
          Qdrant   Neon    LLM
            |        |       |
         RAG DB   App DB   Groq
                          OpenRouter
```

---

# 37. System Architecture – 8 Layers

The architecture diagram divides LawSaathi into **eight major layers**. 

### Layer 1 – User Layer

Interfaces:

* Web application
* Chat interface
* Voice interface
* WhatsApp / other integrations

---

### Layer 2 – API & Gateway Layer

Uses:

**FastAPI**

Responsibilities:

* API gateway
* Request handling
* Authentication
* Rate limiting
* Request validation
* Logging

---

### Layer 3 – Agentic AI Layer

Uses:

**LangGraph**

Components:

* Intent detection
* RAG pipeline
* Tool execution
* Memory manager

This is basically the **brain/orchestration layer**.

---

### Layer 4 – Data & Knowledge Layer

Contains:

**Qdrant**

for vector storage and similarity search.

**Neon PostgreSQL**

for structured application data.

**Firecrawl**

for web search/data extraction.

---

### Layer 5 – Model & LLM Layer

Contains:

**Groq**

Primary.

**OpenRouter**

Fallback/backup.

---

### Layer 6 – Voice & Communication Layer

Contains:

**Sarvam AI**

STT/TTS.

**LiveKit**

Real-time voice communication.

---

### Layer 7 – Observability & Monitoring Layer

Contains:

**LangSmith**

Tracing and debugging.

**Langfuse**

Observability and analytics.

Plus:

* Monitoring
* Logs
* Performance tracking
* Error tracking
* Audit logs

---

### Layer 8 – Deployment Layer

Contains:

**Vercel**

Frontend hosting.

**Render**

Backend hosting.

---

# 38. End-to-End Workflow

The workflow diagram on page 6 is particularly important because it shows how a user query travels through the system. 

Let's convert it into simple steps.

---

## Step 1 – User Input

User sends:

* Text
* Voice

in:

* English
* Hindi
* Kannada

---

## Step 2 – Input Processing

The system performs:

### Language Detection

Determine the language.

### STT

If voice input is provided:

```text
Voice → Text
```

### Normalization

Normalize the user's input into a form suitable for downstream processing.

---

# 39. Step 3 – LangGraph Orchestrator

The request enters:

### LawSaathi LangGraph Orchestrator

This controls the agent workflow.

The orchestrator decides:

> What should happen next?

---

# 40. Step 4 – Intent Detection

The Query Agent identifies:

* Intent
* Entities
* User's legal question

---

# 41. Step 5 – Clarification Decision

The system asks:

### "Need clarification?"

If **Yes**:

```text
Ask user
 ↓
Get additional information
 ↓
Continue processing
```

If **No**:

```text
Continue to retrieval/reasoning
```

This is an important agentic feature because the AI doesn't blindly answer every query.

---

# 42. Step 6 – Planner

The Planner decides which actions are necessary.

Possible actions shown include:

* Legal RAG
* Web Search
* Document Analysis

---

# 43. Step 7 – Legal RAG

The system searches:

### Qdrant

using:

### Embeddings

to find relevant legal knowledge.

---

# 44. Step 8 – Web Search

The system can use:

### Firecrawl

to obtain current information from the web.

This is useful when the question may depend on recent information.

---

# 45. Step 9 – Document Analysis

If the user has uploaded a legal document, the system can analyze it.

For example:

```text
Upload Judgment
       ↓
Extract text
       ↓
Find relevant sections
       ↓
Answer user's question
```

---

# 46. Step 10 – Evidence Filtering & Ranking

This is another important stage.

The system doesn't necessarily treat every retrieved piece of information equally.

It performs:

> **Evidence Filter + Rank**

The purpose is to identify the most relevant evidence before legal reasoning.

---

# 47. Step 11 – Legal Reasoning LLM

The retrieved evidence is passed to the LLM for reasoning.

Conceptually:

```text
Retrieved Evidence
       +
User Question
       +
Conversation Context
       ↓
Legal Reasoning LLM
```

The LLM generates a candidate response based on the available evidence.

---

# 48. Step 12 – Verification

The system then reaches:

### VERIFY

The verifier checks whether the available information is sufficient.

### If sufficient:

```text
Verified
 ↓
Response
```

### If insufficient:

```text
Insufficient
 ↓
Back to retrieval/planning
 ↓
Find additional evidence
 ↓
Reason again
 ↓
Verify again
```

This feedback loop is one of the strongest agentic concepts in the architecture. 

---

# 49. Step 13 – Response

After verification:

```text
Verified Answer
      ↓
Text / Voice Response
```

If voice output is requested:

```text
Text
 ↓
Sarvam TTS
 ↓
Voice
```

The project shows **Text + Voice** as the final response modes. 

---

# 50. Feedback / Self-Reflection Loop

The Agentic AI diagram shows a:

### Feedback Loop / Self-Reflection

This means the system can evaluate intermediate outputs and potentially improve the workflow.

The idea is:

```text
Generate
   ↓
Evaluate
   ↓
Need improvement?
   ↓
Yes → revise/retrieve again
```

This is different from a simple one-shot LLM response. 

---

# 51. Main Features – Complete List

Your Features slide essentially divides the system into **what the project demands** and **what you have decided to build**. 

### Project requirements

1. Multilingual Legal Support
2. Accurate Legal Information
3. Understanding Complex Queries
4. Step-by-Step Guidance
5. Voice Interaction
6. Reliable & Safe Responses
7. Conversation History
8. Document Support

### Decided implementation/features

1. Multilingual Chat
2. Legal Information Retrieval
3. Agentic AI Assistant
4. Case Law & Precedent Search
5. Step-by-Step Guidance
6. Voice Interaction
7. Document Ingestion & Q&A
8. Verified & Safe Responses
9. Chat History & Memory
10. User Preferences