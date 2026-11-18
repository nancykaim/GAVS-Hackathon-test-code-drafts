import json, re, uuid, os, pathlib
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

skill_path = "orchestrator/orchestrator_skill.md"
eg_path = "orchestrator/orchestrator_eg.txt"

os.environ["OLLAMA_API_BASE"] = "http://localhost:11434"

def get_model(role):                      # Qwen is named only here
    return LiteLlm(model="ollama_chat/qwen2.5:7b")

def load_prompt(skill_path, eg_path):
    skill = pathlib.Path(skill_path).read_text()
    examples = pathlib.Path(eg_path).read_text().strip()
    return skill + "\n\n## Examples\n" + examples + "\n"

PROMPT = load_prompt(skill_path, eg_path)

def build_instruction(ctx):               # a function, so JSON braces are not read as state placeholders
    return PROMPT

orchestrator = LlmAgent(
    name="orchestrator",
    model=get_model("orchestrator"),
    instruction=build_instruction,
    generate_content_config=types.GenerateContentConfig(temperature=0),
)

session_service = InMemorySessionService()
runner = Runner(agent=orchestrator, app_name="gauri", session_service=session_service)

async def route(text, retries=1):
    out = ""
    for _ in range(retries + 1):
        sid = str(uuid.uuid4())      # fresh session per message keeps the router stateless
        await session_service.create_session(app_name="gauri", user_id="u1", session_id=sid)
        msg = types.Content(role="user", parts=[types.Part(text=text)])
        out = ""
        async for ev in runner.run_async(user_id="u1", session_id=sid, new_message=msg):
            if ev.is_final_response() and ev.content and ev.content.parts:
                out = ev.content.parts[0].text
        m = re.search(r"\{.*\}", out, re.S)
        try:
            return json.loads(m.group(0)), out
        except Exception:
            continue
    return {"routes": ["CLARIFY"], "animal_mentioned": None, "reason": "invalid JSON"}, out

res, raw = await route("Rani ko kal FMD ka tika laga, 15 November ko.")
print(res)
print(raw)

tests = [
 ("My buffalo Sita delivered a calf yesterday.", ["RECORD"]),
 ("Moti is limping and her leg looks swollen.", ["TRIAGE"]),
 ("Give me medicine for bloat.", ["OUT_OF_SCOPE"]),
 ("Kuch theek nahi hai.", ["CLARIFY"]),
 ("Kali came into heat today and she is also not eating.", ["TRIAGE", "RECORD"]),
]
for text, expected in tests:
    res, raw = await route(text)
    print("OK " if res["routes"] == expected else "BAD", text, "->", res["routes"], "|", res["reason"])

hard = [
 # symptom phrased like a fact
 ("Moti ka doodh kam ho gaya hai.", ["TRIAGE"]),
 ("Sita has a fever since morning.", ["TRIAGE"]),
 # past illness as history only
 ("Rani was sick last month but she is fine now.", ["RECORD"]),
 # facts with no animal named
 ("She got the injection yesterday.", ["CLARIFY"]),
 ("Tika 10 tareekh ko laga tha.", ["CLARIFY"]),
 # two animals in one message
 ("Rani got her shot and Kali is not eating.", ["TRIAGE", "RECORD"]),
 # photo plus record
 ("I am sending a photo of Sita, she calved last week.", ["HEALTH_CHECK", "RECORD"]),
 # not about dairy animals
 ("My goat is not eating.", ["OUT_OF_SCOPE"]),
 ("What is the milk price today?", ["OUT_OF_SCOPE"]),
 # contradictory
 ("Rani was vaccinated yesterday and she has never been vaccinated.", ["CLARIFY"]),
 # asks about dose in another phrasing
 ("Kitni goli deni chahiye bukhar mein?", ["OUT_OF_SCOPE"]),
 # greeting or empty
 ("Hello", ["CLARIFY"]),
]

for text, expected in hard:
    res, raw = await route(text)
    print("OK " if res["routes"] == expected else "BAD", text, "->", res["routes"], "|", res["reason"])
