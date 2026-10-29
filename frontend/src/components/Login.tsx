import { FormEvent, useState } from "react";
import { entrarComoInvitado, login, register } from "../auth";

interface Props {
  onAuthenticated: () => void;
}

export default function Login({ onAuthenticated }: Props) {
  const [modo, setModo] = useState<"login" | "registro">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function entrar(accion: () => Promise<unknown>) {
    setCargando(true);
    setError(null);
    try {
      await accion();
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ocurrió un error inesperado.");
    } finally {
      setCargando(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    entrar(() => (modo === "login" ? login(email, password) : register(email, password)));
  }

  return (
    <div className="acceso">
      <header className="sitio-cabecera">
        <p className="logotipo">Amate</p>
      </header>

      <main>
        <section className="portada">
          <div className="marco">
            <h1>{modo === "login" ? "Consulta las leyes de Guerrero con el artículo a la vista." : "Crea tu cuenta de Amate."}</h1>
            <p>
              {modo === "login"
                ? "Entra con tu correo o consulta sin cuenta. Amate responde sobre la legislación estatal y federal que aplica en Guerrero."
                : "Usa tu correo de trabajo. Esta es una versión de prueba para abogados."}
            </p>
          </div>
        </section>

        <section className="banda">
          <div className="marco">
            <form className="tarjeta" onSubmit={handleSubmit}>
              <label className="field">
                <span>Correo electrónico</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                />
              </label>

              <label className="field">
                <span>Contraseña{modo === "registro" && " (mínimo 8 caracteres)"}</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  autoComplete={modo === "login" ? "current-password" : "new-password"}
                />
              </label>

              {error && <div className="error-panel">{error}</div>}

              <button type="submit" className="primary-button" disabled={cargando}>
                {cargando ? "Un momento…" : modo === "login" ? "Entrar" : "Crear cuenta"}
              </button>

              <button type="button" className="boton-secundario boton-invitado" disabled={cargando} onClick={() => entrar(entrarComoInvitado)}>
                Consultar sin cuenta
              </button>

              <button
                type="button"
                className="enlace acceso-cambio"
                onClick={() => {
                  setModo(modo === "login" ? "registro" : "login");
                  setError(null);
                }}
              >
                {modo === "login" ? "¿No tienes cuenta? Crear una" : "¿Ya tienes cuenta? Entrar"}
              </button>
            </form>
          </div>
        </section>
      </main>
    </div>
  );
}
