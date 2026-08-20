# Hospital Policy + CKAI Prototype: Technical Specification

> **Status: Proposed initial draft**
>
> This specification is intentionally lightweight. The aim is to create a prototype that can be built and run locally with minimal complexity, while also being straightforward to host for SME and user testing.

## 1. Technical Objective

Build one lightweight Python-based prototype application that supports two distinct experiences:

- Physician
- Nurse

The user can switch between the two experiences using a tab or equivalent control at the top of the interface.

The application should:

- Accept a user question through a conversational interface
- Use the selected experience to determine which CKAI variant and prompt flow are used
- Send the user question to CKAI and the exemplar policy retrieval pipeline in parallel
- Fetch the CKAI answer
- Use the CKAI answer, where useful, to further refine retrieval from the policy dataset
- Use the CKAI answer and retrieved policy content as inputs to the selected response-generation prompt flow
- Present the resulting response to the user
- Be runnable locally
- Be deployable as a single hosted application for SME and user testing

## 2. Physician And Nurse Experiences

The application will contain two selectable experiences.

### Physician Experience

The physician experience will use:

- The physician CKAI variant
- The physician prompt flow
- Physician-specific presentation components where needed

### Nurse Experience

The nurse experience will use:

- The nurse CKAI variant
- The nurse prompt flow
- Nurse-specific presentation components where needed

The surrounding application and shared technical components should be reused between both experiences.

## 3. Proposed Architecture

```text
                         Single hosted application
                                  |
                         HTML/CSS interface
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             Physician tab                 Nurse tab
                    |                           |
                    +-------------+-------------+
                                  |
                         Selected experience
                                  |
                              User question
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
               CKAI request              Policy retrieval
          (variant selected by                |
               experience)                    v
                    |                 Initial policy results
                    |                           |
                    v                           |
               CKAI answer --------------------+
                    |
                    v
         Optional refinement of policy
         retrieval using CKAI response
                    |
                    v
            Final policy results
                    |
                    v
         Experience-specific prompt flow
                    |
                    v
               Final response
                    |
                    v
               HTML/CSS UI
```

## 4. Swappable Experience Components

The prototype should reuse shared application code while swapping the components that differ between the physician and nurse experiences.

The selected experience should determine:

- CKAI variant
- Prompt flow
- Experience-specific response presentation where needed

Shared components should be used for both experiences wherever possible.

## 5. CKAI Integration

The user question must be sent to CKAI as part of the initial processing of the question.

The CKAI variant depends on the currently selected experience:

- Physician experience uses the physician CKAI variant
- Nurse experience uses the nurse CKAI variant

The CKAI request should run in parallel with the initial policy retrieval process.

Once the CKAI answer is returned, it can be used to further refine retrieval against the exemplar policy dataset before the final policy content is passed into the selected prompt flow.

## 6. Exemplar Policy Library

The prototype will use a defined set of exemplar hospital institutional policies.

These policies will form the policy library used during prototyping.

The prototype needs a retrieval strategy that can identify policy content relevant to the user's question.

The initial retrieval can use the user's question directly.

The CKAI answer can then be used, where useful, to further refine retrieval from the policy dataset.

For the prototype, the retrieval approach should remain as simple as practical. The exact approach will depend on what is achievable during implementation.

## 7. Prompt Flows

The physician and nurse experiences will have separate prompt flows.

The selected experience determines which prompt flow is used.

Each prompt flow will receive:

- The user question
- The relevant CKAI answer
- Retrieved content from the exemplar hospital policies

These inputs will be used to generate the response shown to the user.

## 8. Front-End And Conversational Interface

The prototype will use an HTML and CSS front end.

The interface should:

- Provide a top-level control for switching between the Physician and Nurse experiences
- Allow users to enter questions
- Present generated responses
- Apply the selected experience without requiring a separate application or URL
- Be suitable for hosted SME and user testing

## 9. Local Development And Hosting

The prototype should be buildable and runnable locally during development.

Hosting should remain simple. The prototype should be deployed as a single application rather than separate physician and nurse deployments.

The same hosted application should support both experiences through the interface-level experience selector.
