import { useEffect, useState, type FormEvent } from "react";

type Config = {
  agent_name: string;
  greeting: string;
  voice: string;
  instructions: string;
  enabled_tools: string[];
};

type Options = {
  tools: { name: string; description: string }[];
  voices: { id: string; label: string }[];
  call_rules: string;
};

const API_DOWN = "Could not reach the API. Start it with: uv run uvicorn api.server:app --port 8000";

// FastAPI sends a string for our own errors and a list of field errors when validation fails.
function errorMessage(detail: string | { loc: string[]; msg: string }[]): string {
  if (typeof detail === "string") return detail;
  return detail.map((error) => `${error.loc.slice(1).join(".")}: ${error.msg}`).join("\n");
}

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([fetch("/api/config"), fetch("/api/options")])
      .then(async ([configResponse, optionsResponse]) => {
        if (!configResponse.ok || !optionsResponse.ok) throw new Error();
        setConfig(await configResponse.json());
        setOptions(await optionsResponse.json());
      })
      .catch(() => setError(API_DOWN));
  }, []);

  if (!config || !options) {
    return <main>{error ? <p className="error">{error}</p> : <p>Loading...</p>}</main>;
  }

  const update = (change: Partial<Config>) => {
    setConfig({ ...config, ...change });
    setSaved(false);
  };

  const toggleTool = (name: string, enabled: boolean) => {
    const others = config.enabled_tools.filter((tool) => tool !== name);
    update({ enabled_tools: enabled ? [...others, name] : others });
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      const body = await response.json();
      if (response.ok) {
        setConfig(body);
        setSaved(true);
      } else {
        setError(errorMessage(body.detail));
      }
    } catch {
      setError(API_DOWN);
    } finally {
      setSaving(false);
    }
  };

  return (
    <main>
      <h1>Receptionist settings</h1>
      <p>Changes apply to the next call. A call already in progress keeps the settings it started with.</p>

      <form onSubmit={save}>
        <label>
          Agent name
          <input value={config.agent_name} onChange={(e) => update({ agent_name: e.target.value })} />
        </label>

        <label>
          Greeting (the first thing the agent says)
          <textarea rows={2} value={config.greeting} onChange={(e) => update({ greeting: e.target.value })} />
        </label>

        <label>
          Voice
          <select value={config.voice} onChange={(e) => update({ voice: e.target.value })}>
            {options.voices.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Instructions
          <textarea
            rows={18}
            value={config.instructions}
            onChange={(e) => update({ instructions: e.target.value })}
          />
        </label>
        <p className="hint">
          In the greeting and the instructions, <code>{"{agent_name}"}</code> is replaced with the agent name.
        </p>

        <h2>Call rules</h2>
        <p className="hint">
          These rules are always added after your instructions. They keep the phone style and the safety rules in
          place, so they cannot be edited here.
        </p>
        <pre>{options.call_rules}</pre>

        <fieldset>
          <legend>Tools the agent can use</legend>
          {options.tools.map((tool) => (
            <label key={tool.name}>
              <input
                type="checkbox"
                checked={config.enabled_tools.includes(tool.name)}
                onChange={(e) => toggleTool(tool.name, e.target.checked)}
              />{" "}
              <code>{tool.name}</code>: {tool.description}
            </label>
          ))}
        </fieldset>

        <button disabled={saving}>{saving ? "Saving..." : "Save"}</button>
        {saved && <p className="saved">Saved. The next call will use these settings.</p>}
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  );
}
