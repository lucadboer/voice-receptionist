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

const API_DOWN = "Could not reach the API. Start the API and this page together with: make admin";

// FastAPI sends a string for our own errors and a list of field errors when validation fails.
function errorMessage(detail: string | { loc: string[]; msg: string }[]): string {
  if (typeof detail === "string") return detail;
  return detail.map((error) => `${error.loc.slice(1).join(".")}: ${error.msg}`).join("\n");
}

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [lastSaved, setLastSaved] = useState<Config | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([fetch("/api/config"), fetch("/api/options")])
      .then(async ([configResponse, optionsResponse]) => {
        if (!configResponse.ok || !optionsResponse.ok) throw new Error();
        const loaded = await configResponse.json();
        setConfig(loaded);
        setLastSaved(loaded);
        setOptions(await optionsResponse.json());
      })
      .catch(() => setError(API_DOWN));
  }, []);

  if (!config || !options) {
    return <main>{error ? <p role="alert" className="error">{error}</p> : <p>Loading...</p>}</main>;
  }

  const changed = JSON.stringify(config) !== JSON.stringify(lastSaved);

  const update = (change: Partial<Config>) => {
    setConfig({ ...config, ...change });
    setSaved(false);
  };

  // Keep the tools in the order of the options, so turning a tool off and on again is not a change.
  const toggleTool = (name: string, enabled: boolean) => {
    const names = options.tools.map((tool) => tool.name);
    update({ enabled_tools: names.filter((tool) => (tool === name ? enabled : config.enabled_tools.includes(tool))) });
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
        setLastSaved(body);
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

  const status = changed ? "Unsaved changes" : saved ? "Saved. The next call will use these settings." : "";

  return (
    <main>
      <h1>Receptionist settings</h1>
      <p>Changes apply to the next call. A call already in progress keeps the settings it started with.</p>

      <form onSubmit={save}>
        <section>
          <h2>Persona</h2>
          <label htmlFor="agent-name">Agent name</label>
          <input
            id="agent-name"
            required
            maxLength={40}
            value={config.agent_name}
            onChange={(e) => update({ agent_name: e.target.value })}
          />

          <label htmlFor="greeting">Greeting</label>
          <p id="greeting-hint" className="hint">
            The first thing the agent says. <code>{"{agent_name}"}</code> is replaced with the agent name.
          </p>
          <textarea
            id="greeting"
            rows={3}
            required
            maxLength={300}
            aria-describedby="greeting-hint"
            value={config.greeting}
            onChange={(e) => update({ greeting: e.target.value })}
          />

          <label htmlFor="voice">Voice</label>
          <select id="voice" value={config.voice} onChange={(e) => update({ voice: e.target.value })}>
            {options.voices.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.label}
              </option>
            ))}
          </select>
        </section>

        <section>
          <h2>Instructions</h2>
          <label htmlFor="instructions">Agent instructions</label>
          <p id="instructions-hint" className="hint">
            What the agent does on a call. <code>{"{agent_name}"}</code> works here too.
          </p>
          <textarea
            id="instructions"
            rows={18}
            required
            maxLength={8000}
            aria-describedby="instructions-hint"
            value={config.instructions}
            onChange={(e) => update({ instructions: e.target.value })}
          />

          <details>
            <summary>Call rules (always added, read-only)</summary>
            <p className="hint">
              These rules are always added after your instructions. They keep the phone style and the safety rules in
              place, so they cannot be edited here.
            </p>
            <pre>{options.call_rules}</pre>
          </details>
        </section>

        <section>
          <fieldset>
            <legend>
              <h2>Tools</h2>
            </legend>
            {options.tools.map((tool) => (
              <label key={tool.name} className="tool">
                <input
                  type="checkbox"
                  checked={config.enabled_tools.includes(tool.name)}
                  onChange={(e) => toggleTool(tool.name, e.target.checked)}
                />
                <span>
                  <code>{tool.name}</code>
                  <span className="hint">{tool.description}</span>
                </span>
              </label>
            ))}
          </fieldset>
        </section>

        <div className="save-bar">
          <button disabled={saving || !changed}>{saving ? "Saving..." : "Save changes"}</button>
          <p role="status" className={saved ? "saved" : undefined}>{status}</p>
          {error && <p role="alert" className="error">{error}</p>}
        </div>
      </form>
    </main>
  );
}
