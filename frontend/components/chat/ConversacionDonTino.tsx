"use client";
import { useEffect, useRef, useState, type RefObject } from "react";
import { Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { RobotMini } from "@/components/RobotMascot";
import { BotonCopiar, RespuestaDelBot } from "@/components/chat/RespuestaDelBot";
import { useDonTino } from "@/store/donTino";

/**
 * Los mensajes, las sugerencias y el campo para escribirle a Don Tino. Es el
 * chat que vivía en Inicio, sacado a un componente el 25/11/2026 para usarlo
 * también en la burbuja de abajo a la derecha (components/layout/BurbujaDonTino):
 * la conversación es una sola (store/donTino), así que se ve la misma en los
 * dos lados.
 */
export function ConversacionDonTino({ claseMensajes, campoRef }: {
  /** El alto del área de mensajes (en Inicio, hasta 60vh; en la burbuja, lo que quede). */
  claseMensajes: string;
  /** Para poner el foco en el campo al abrir la burbuja. */
  campoRef?: RefObject<HTMLInputElement>;
}) {
  const { t } = useTranslation();
  const mensajes = useDonTino((s) => s.mensajes);
  const escribiendo = useDonTino((s) => s.escribiendo);
  const enviar = useDonTino((s) => s.enviar);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const SUGGESTIONS = [
    t("home.suggestions.s1"),
    t("home.suggestions.s2"),
    t("home.suggestions.s3"),
    t("home.suggestions.s4"),
  ];
  const error = "Lo siento, hubo un error al contactar el asistente. Intentá de nuevo.";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [mensajes, escribiendo]);

  function send(text: string) {
    if (!text.trim()) return;
    setInput("");
    void enviar(text, error);
  }

  return (
    <>
      <div className={`border-t border-slate-100 dark:border-slate-700 px-5 py-4 space-y-4 overflow-y-auto bg-slate-50/50 dark:bg-slate-900/50 ${claseMensajes}`}>
        {mensajes.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            {m.role === "bot" && (
              <div className="w-7 h-7 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0 mt-0.5">
                <RobotMini />
              </div>
            )}
            {/* El tope de ancho va en la columna: en el globo era el 85% de su
                propia columna y partía hasta un «Hola» en «Ho / la». */}
            <div className={`flex min-w-0 max-w-[85%] flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
              <div className={`max-w-full px-4 py-2.5 rounded-2xl text-sm leading-relaxed break-words ${
                m.role === "user"
                  ? "bg-brand-600 text-white rounded-tr-sm whitespace-pre-wrap"
                  : "bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-700 text-slate-700 dark:text-slate-300 rounded-tl-sm shadow-sm"
              }`}>
                {/* Lo del bot viene en markdown (negritas, listas, links a las
                    acciones); lo de la persona se muestra tal cual lo escribió. */}
                {m.role === "bot" ? <RespuestaDelBot texto={m.text} /> : m.text}
              </div>
              {m.role === "bot" && i > 0 && (
                <div className="mt-1 flex items-center gap-2 px-1">
                  <BotonCopiar texto={m.text} />
                  {m.usage && (
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">
                      {m.usage.total_tokens.toLocaleString()} tokens
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {escribiendo && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0">
              <RobotMini />
            </div>
            <div className="bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-700 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm flex gap-1 items-center">
              <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {mensajes.length <= 1 && (
        <div className="px-5 py-3 flex gap-2 flex-wrap border-t border-slate-100 dark:border-slate-700">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" onClick={() => send(s)}
              className="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-brand-400 hover:text-brand-600 hover:bg-brand-50 transition-all">
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={(e) => { e.preventDefault(); send(input); }}
        className="border-t border-slate-100 dark:border-slate-700 flex gap-3 px-4 py-3"
      >
        <input
          ref={campoRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("home.inputPlaceholder")}
          aria-label={t("home.inputPlaceholder")}
          className="min-w-0 flex-1 text-base sm:text-sm bg-slate-100 dark:bg-slate-800 rounded-xl px-4 py-2.5 text-slate-800 dark:text-slate-200 placeholder:text-slate-500 dark:placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:bg-white dark:focus:bg-slate-900 transition-all"
        />
        <button
          type="submit"
          disabled={!input.trim() || escribiendo}
          aria-label={t("donTino.enviar", "Enviar")}
          className="w-10 h-10 rounded-xl bg-brand-600 flex items-center justify-center text-white disabled:opacity-40 hover:bg-brand-700 transition-colors shrink-0"
        >
          <Send size={15} />
        </button>
      </form>
    </>
  );
}
