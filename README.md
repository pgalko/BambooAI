# BambooAI
A lightweight library utilizing Large Language Models (LLMs) to provide natural language interaction capabilities, much like a research and data analysis assistant enabling conversation with your data. You can either provide your own data sets, or allow the library to locate and fetch data for you. It supports Internet searches and external API interactions.

## Objective

The BambooAI library is a experimental, lightweigh tool that utilizes Large Language Models (LLMs) to facilitate data analysis, making it more accessible to users, including those without programming expertise. It functions as an assistant for research and data analysis, allowing users to interact with their data through natural language. Users can supply their own datasets or BambooAI can assist in sourcing the necessary data. The tool also integrates internet searches and accesses external APIs to enhance its functionality.

BambooAI processes natural language queries about datasets and can generate and execute Python code for data analysis and visualization. This enables users to derive insights from their data without extensive coding knowledge. Users simply input their dataset, ask questions in simple English, and BambooAI provides the answers, along with visualizations if needed, to help understand the data better.

BambooAI aims to augment the capabilities of data analysts across all levels. It simplifies data analysis and visualization, helping to streamline workflows. The library is designed to be user-friendly, efficient, and adaptable to meet various needs.

## Preview

**Try it out in Google Colab:**

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1grKtqKD4u8cVGMoVv__umci4F7IU14vU?usp=sharing)


**A Machine Learning Example using supplied dataframe:**
```
!pip install pandas
!pip install bambooai

import pandas as pd
from bambooai import BambooAI

df = pd.read_csv('titanic.csv')
bamboo = BambooAI(df, debug=True, vector_db=False, search_tool=True)
bamboo.pd_agent_converse()
```
**Jupyter Notebook:** 

_Task: Can you please devise a machine learnig model to predict the survival of passengers on the Titanic? 
Output the accuracy of the model. Plot the confusion matrix, correlation matrix, and other relevant metrics. Search internet for the best approach to this task._


https://github.com/pgalko/BambooAI/assets/39939157/6058a3a2-63d9-44b9-b065-0a0cda5d7e17

**Web UI:**

_Task: Various queries related to sports data analysis_

https://github.com/user-attachments/assets/fa735fce-9645-4a22-af02-e40579acd53d



## How it works

The BambooAI agent operates through several key steps to interact with users and generate responses:

**1. Initiation**
- The user launches the BambooAI agent with a question.
- If no initial question is provided, the agent prompts the user for a question or an 'exit' command to terminate the program.
- The agent then enters a loop where it responds to each question provided, and upon completion, prompts the user for the next question. This loop continues until the user chooses to exit the program.

**2. Task Evaluation**
- The agent stores the received question and utilizes the Large Language Model (LLM) to evaluate and categorize it.
- The LLM determines whether the question necessitates a textual response, additional information (Google search: https://serper.dev/), or can be resolved using code.
- Depending on the task evaluation and classification the agent calls the appropriate agent.

**3. Dynamic Prompt Build**
- If the question can be resolved by code, the agent determines whether the necessary data is contained within the provided dataset, requires downloading from an external source, or if the question is of a generic nature and data is not required.
- The agent then chooses its approach accordingly. It formulates an algorithm, expressed as a task list, to serve as a blueprint for the analysis.
- The original question is modified to align with this algorithm. The agent performs a semantic search against a vector database for similar questions.
- Any matching questions found are appended to the prompt as examples. GPT-3.5, GPT-4 or a local OSS model is then used to generate code based on the algorithm.

**4. Debugging, Execution, and Error Correction**
- If the generated code needs debugging, GPT-4 is engaged.
- The code is executed, and if errors occur, the agent logs the error message and refers it back to the LLM for correction.
- This process continues until successful code execution.

**5. Results, Ranking, and Knowledge Base Build**
- Post successful execution, GPT-4 is used to rank the answer.
- If the rank surpasses a set threshold, the question, answer, code, and rank are stored in the Pinecone vector database.
- Regardless of the rank, the final answer or visualization is formatted and presented to the user.

**6. Human Feedback and Loop Continuation**
- The agent seeks feedback from the user.
- If the user validates the auto-generated ranking, the question/answer pair is stored in the vector database.
- If not, a new execution loop begins.

Throughout this process, the agent continuously solicits user input, stores messages for context, and generates and executes code to ensure optimal results. Various AI models and a vector database are employed in this process to provide accurate and helpful responses to user's questions.

**Flow chart (General agent flow):**

![](images/BambooAI_Agent_Flow.png)

## Supported vendors/models

The library supports use of various open source or proprietary models, either via API or localy.

**API:**
- OpenAI - All models
- Google - Gemini Models
- Anthropic - All Models
- Groq - All Models
- Mistral - All Models

**Local:**
- Ollama - All Models
- A Selection of local models(more info below)

You can specify what vendor/model you want to use for a specific agent by modifying the content of LLM_CONFIG file, replacing the default OpenAI model name with the model and vendor of your choicee. eg. ```{"agent": "Code Generator", "details": {"model": "open-mixtral-8x22b", "provider":"mistral","max_tokens": 4000, "temperature": 0}}```. The purpose of LLM_CONFIG is described in more detail below.

## How to use

**Installation**

```
pip install bambooai
```

**Usage**

- Parameters

```
df: pd.DataFrame - Dataframe (It will try to source the data from internet, if 'df' is not provided)

max_conversations: int - Number of "user:assistant" conversation pairs to keep in memory for a context. Default=4

debug: bool - If True, the received code is sent back to the LLM for evaluation of its relevance to the user's question, along with code error checking and debugging.

search_tool: bool - If True, the Planner agent will use a "google search API: https://serper.dev/" if the required information is not available or satisfactory. By default it only support HTML sites, but can be enhanced with Selenium if the ChromeDriver exists on the system (details below).

vector_db: bool - If True, each answer will first be ranked from 1 to 10. If the rank surpasses a certain threshold (8), the corresponding question (vectorised), plan, code, and rank (metadata) are all stored in the Pinecone database. Each time a new question is asked, these records will be searched. If the similarity score is above 0.9, they will be offered as examples and included in the prompt (in a one-shot learning scenario)

df_onthology: bool - If True, the onthology defined in the module `df_onthology.py` will be used to inform LLM of the dataframe structure, metrics, record frequency, keys, joins, abstract functions etc. The onthology is custom for each dataframe type, and needs to be defined by the user. Sample onthology is included. This feature signifficantly improves performance, and quality of the solutions.

exploratory: bool - If set to True, the LLM will evaluate the user's question and select an "Expert" that is best suited to address the question (experts: Research Specialist, Data Analyst). In addition, if the task involves code generation/execution, it will generate a task list detailing the steps, which will subsequently be sent to the LLM as a part of the prompt for the next action. This method is particularly effective for vague user prompts, but it might not perform as efficiently with more specific prompts. The default setting is True.

e.g. bamboo = BambooAI(df, debug=True, vector_db=True, search_tool=True, exploratory=True)
     bamboo = BambooAI(df,debug=False, vector_db=False, exploratory=True, search_tool=True)
```

***Deprecation Notice (October 25, 2023):***
*Please note that the "llm", "local_code_model", "llm_switch_plan", and "llm_switch_code" parameters have been deprecated as of v 0.3.29. The assignment of models and model parameters to agents is now handled via LLM_CONFIG. This can be set either as an environment variable or via a LLM_CONFIG.json file in the working directory. Please see the details below*

- LLM Config

The agent specific llm configuration is stored in ```LLM_CONFIG``` environment variable, or in the "LLM_CONFIG.json file which needs to be stored in the BambooAI's working directory. The config is in a form of JSON list of dictionaries and specifies model name, provider, temperature and max_tokens for each agent. You can use the provided LLM_CONFIG_sample.json as a starting point, and modify the config to reflect your preferences. If neither "ENV VAR" nor "LLM_CONFIG.json" is present, BambooAI will use the default hardcoded configuration that uses "gpt-3.5-turbo" for all agents.

- Prompt Templates

The BambooAI library uses default hardcoded set of prompt templates for each agent. If you want to experiment with them, you can modify the provided "PROMPT_TEMPLATES_sample.json" file, remove the "_sample from its name and store in the working directory. Subsequently, the content of the modified "PROMPT_TEMPLATES.json" will be used instead of the hardcoded defaults. You can always revert back to default prompts by removing/renaming the modified "PROMPT_TEMPLATES.json".

- Example usage: Run in a loop

```
# Run in a loop remembering the conversation history
import pandas as pd
from bambooai import BambooAI

df = pd.read_csv('test_activity_data.csv')
bamboo = BambooAI(df)
bamboo.pd_agent_converse()
```
- Example Usage: Single execution
```
# Run programaticaly (Single execution).
import pandas as pd
from bambooai import BambooAI

df = pd.read_csv('test_activity_data.csv')
bamboo = BambooAI(df)
bamboo.pd_agent_converse("Calculate 30, 50, 75 and 90 percentiles of the heart rate column")
```

**Environment Variables**

The library requires an OpenAI API account and the API key to connect to OpenAI LLMs. The OpenAI API key needs to be stored in a ```OPENAI_API_KEY``` environment variable.
The key can be obtained from here: https://platform.openai.com/account/api-keys.

In addition to OpenAI models a selection of models from different providers is also supported (Groq, Gemini, Mistral, Anthropic). The API keys needs to be stored in environment variables in the following format ```<VENDOR_NAME>_API_KEY```.
You need to use ```GEMINI_API_KEY``` for Google Gemini models. 

As mentioned above, the llm config can be stored in a string format in the  ```LLM_CONFIG``` environment variable. You can use the content of the provided LLM_CONFIG_sample.json as a starting point and modify to your preference, depending on what models you have access to. 

The Pincone vector db is optional. If you don want to use it, you dont need to do anything. If you have an account with Pinecone and would like to use the knowledge base and ranking features, you will be required to setup ```PINECONE_API_KEY``` envirooment variable, and set the 'vector_db' parameter to True. The vector db index is created upon first execution.

The Google Search is also optional. If you don want to use it, you dont need to do anything. If you have an account with Serper and would like to use the Google Search functionality, you will be required to setup and account with ": https://serper.dev/", and set ```SERPER_API_KEY``` environment variable, and set the 'search_tool' parameter to True. By default bambooai can only scrape websites with HTML content. However it is also capable of using Selenium with ChromeDriver, which is much more powerfull. To enable this functionality you will need to manualy download a version of ChromeDriver that matches your version of the Chrome browser, store it on the filesystem and create an environment variable ```SELENIUM_WEBDRIVER_PATH``` with a path to your ChromeDriver. BambooAI wil pick it up automaticaly, and use Selenium for all scraping tasks.

**Local Open Source Models**

The library currently directly supports the following open-source models. I have selected the models that currently score the highest on the HumanEval benchmark.
- **WizardCoder(WizardLM):** WizardCoder-15B-V1.0, WizardCoder-Python-7B-V1.0, WizardCoder-Python-13B-V1.0, WizardCoder-Python-34B-V1.0
- **WizardCoder GPTQ(TheBloke):** WizardCoder-15B-1.0-GPTQ, WizardCoder-Python73B-V1.0-GPTQ, WizardCoder-Python-13B-V1.0-GPTQ, WizardCoder-Python-34B-V1.0-GPTQ
- **CodeLlama Instruct(TheBloke):** CodeLlama-7B-Instruct-fp16, CodeLlama-13B-Instruct-fp16, CodeLlama-34B-Instruct-fp16
- **CodeLlama Instruct(Phind):** Phind-CodeLlama-34B-v2
- **CodeLlama Completion(TheBloke):** CodeLlama-7B-Python-fp16, CodeLlama-13B-Python-fp16, CodeLlama-34B-Python-fp16

If you want to use the local model for a specific agent, modify the LLM_CONFIG content replacing the OpenAI model name with the local model name and change the provider value to 'local'. eg. ```{"agent": "Code Generator", "details": {"model": "Phind-CodeLlama-34B-v2", "provider":"local","max_tokens": 2000, "temperature": 0}}```
At present it is recommended to use local models only for code generation tasks, all other tasks like pseudo code generaration, summarisation, error correction and ranking should be still handled by OpenAI models of choice. The model is downloaded from Huggingface and cached localy for subsequent executions. For a reasonable performance it requires CUDA enabled GPU and the pytorch library compatible with the CUDA version. Below are the required libraries that are not included in the package and will need to be installed independently:
```
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 (Adjust to match your CUDA version. This library is already included in Colab notebooks)
pip install auto-gptq (Only required if using WizardCoder-15B-1.0-GPTQ model)
pip install accelerate
pip install einops
pip install xformers
pip install bitsandbytes
```
The settings and parameters for local models are located in local_models.py module and can be adjusted to match your particular configuration or preferences.

**Ollama**

The library also supports the use of Ollama https://ollama.com/ and all of it's models. If you want to use a local Ollama model for a specific agent, modify the LLM_CONFIG content replacing the OpenAI model name with the Ollama model name and change the provider value to 'ollama'. eg. ```{"agent": "Code Generator", "details": {"model": "llama3:70b", "provider":"ollama","max_tokens": 2000, "temperature": 0}}```

**Logging**

All LLM interactions (local or via APIs) are logged in the `bambooai_consolidated_log.json` file. When the size of the log file reaches 5 MB, a new log file is created. A total of 3 log files are kept on the file system before the oldest file gets overwritten.

The following details are captured:

- **Chain ID**
- **All LLM calls (steps) within the chain**, including details of each call eg. agent name, timestamp, model, prompt (context memory), response, token use, cost, tokens per second etc. 
- **Chain summary**, including token use, cost, count of llm calls, tokens per second etc.
- **Summary per LLM**, including token use, cost, number of calls, tokens per second etc.

Log Structure:
```
- chain_id: 1695375585
  ├─ chain_details (LLM Calls)
  │   ├─ List of Dictionaries (Multiple Steps)
  │       ├─ Call 1
  │       │   ├─ agent (String)
  │       │   ├─ chain_id (Integer)
  │       │   ├─ timestamp (String)
  │       │   ├─ model (String)
  │       │   ├─ messages (List)
  │       │   │   └─ role (String)
  │       │   │   └─ content (String)
  │       │   └─ Other Fields (content, prompt_tokens, completion_tokens, total_tokens, elapsed_time, tokens_per_second, cost)
  │       ├─ Call 2
  │       │   └─ ... (Similar Fields)
  │       └─ ... (Call 3, Call 4, Call 5 ...)
  │
  ├─ chain_summary
  │   ├─ Dictionary
  │       ├─ Total LLM Calls (Integer)
  │       ├─ Prompt Tokens (Integer)
  │       ├─ Completion Tokens (Integer)
  │       ├─ Total Tokens (Integer)
  │       ├─ Total Time (Float)
  │       ├─ Tokens per Second (Float)
  │       ├─ Total Cost (Float)
  │
  ├─ summary_per_model
      ├─ Dictionary
          ├─ LLM 1 (Dictionary)
          │   ├─ LLM Calls (Integer)
          │   ├─ Prompt Tokens (Integer)
          │   ├─ Completion Tokens (Integer)
          │   ├─ Total Tokens (Integer)
          │   ├─ Total Time (Float)
          │   ├─ Tokens per Second (Float)
          │   ├─ Total Cost (Float)
          ├─ LLM 2
          |   └─ ... (Similar Fields)
          └─ ... (LLM 3, LLM 4, LLM 5 ...)
```

## Performance Comparison (3rd May 2024)

**Task:** _Devise a machine learning model to predict the survival of passengers on the Titanic. The output should include the accuracy of the model and visualizations of the confusion matrix, correlation matrix, and other relevant metrics._

**Dataset:** _Titanic.csv_

**Model:** _GPT-4-Turbo_

### **_OpenAI Assistants API (Code Interpreter)_**
- **Result:**
  - **Confusion Matrix:**
    - **True Negative (TN):** 90 passengers were correctly predicted as not surviving.
    - **True Positive (TP):** 56 passengers were correctly predicted as surviving.
    - **False Negative (FN):** 18 passengers were incorrectly predicted as not surviving.
    - **False Positive (FP):** 15 passengers were incorrectly predicted as surviving.
    
| Metric         | Value        |
| -------------- | ------------ |
| Execution Time | 77.12 seconds|
| Input Tokens   | 7128         |
| Output Tokens  | 1215         |
| Total Cost     | $0.1077      |


### **_BambooAI (No Planning, Google Search or Vector DB)_**
- **Result:**
  - **Confusion Matrix:**
    - **True Negative (TN):** 92 passengers were correctly predicted as not surviving.
    - **True Positive (TP):** 55 passengers were correctly predicted as surviving.
    - **False Negative (FN):** 19 passengers were incorrectly predicted as not surviving.
    - **False Positive (FP):** 13 passengers were incorrectly predicted as surviving.
    

| Metric         | Value        |
| -------------- | ------------ |
| Execution Time | 47.39 seconds|
| Input Tokens   | 722          |
| Output Tokens  | 931          |
| Total Cost     | $0.0353      |


## Notes

- The library currently supports OpenAI Chat models. It has been tested with both gpt-3.5-turbo and gpt-4. The gpt-3.5-turbo seems to perform OK for simpler tasks and is the good starting/exploration option due to its 10x lower cost.
- It can also be used with models from the following vendors via API. Anthropic, Mistral, Google Gemini, Groq. All you need is the API key.
- Also the use of Ollama and all of it's models is supported. This could be quite handy as a buch of Llama 3 finetunes are about to start landing.
- For coding tasks it also supports SOTA open source code models like CodeLlama and WizardCoder.
- The library executes LLM generated Python code, this can be bad if the LLM generated Python code is harmful. Use cautiously.
- Be sure to monitor your token usage. At the time of writing, the cost per 1K input tokens is $0.01 USD for GPT-4-turbo and $0.001 USD for GPT-3.5-turbo. It's important to keep these costs in mind when using the library, particularly when using the more expensive models.
- Supported OpenAI models: *gpt-3.5-turbo, gpt-3.5-turbo-613, gpt-3.5-turbo-16k, gpt-4, gpt-4-turbo.*
- Supported Open Source Models: *WizardCoder-15B-V1.0, WizardCoder-Python-7B-V1.0, WizardCoder-Python-13B-V1.0, WizardCoder-Python-34B-V1.0, WizardCoder-15B-1.0-GPTQ, WizardCoder-Python73B-V1.0-GPTQ, WizardCoder-Python-13B-V1.0-GPTQ,
  WizardCoder-Python-34B-V1.0-GPTQ, CodeLlama-7B-Instruct-fp16, CodeLlama-13B-Instruct-fp16, CodeLlama-34B-Instruct-fp16, CodeLlama-7B-Python-fp16, CodeLlama-13B-Python-fp16, CodeLlama-34B-Python-fp16, Phind-CodeLlama-34B-v2.*

## Contributing

Contributions are welcome; please feel free to open a pull request. Keep in mind that our goal is to maintain a concise codebase with high readability.

## ToDo

- A lot :-)


