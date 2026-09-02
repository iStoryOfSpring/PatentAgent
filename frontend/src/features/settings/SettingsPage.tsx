import { ExternalLink, Power, Settings2 } from "lucide-react";
import type { ProviderProfile } from "../../types";
import { protocolLabel } from "../../uiLabels";
import { useI18n } from "../../i18n";

export function SettingsPage({ profile, connected, onOpen, onDisconnect }: {
  profile?: ProviderProfile;
  connected: boolean;
  onOpen: () => void;
  onDisconnect: () => void;
}) {
  const { locale, t } = useI18n();
  return <div className="h-full overflow-y-auto p-5 md:p-8"><div className="mx-auto max-w-4xl"><h1 className="text-2xl font-bold">{t("settings.title")}</h1><p className="mt-1 text-sm text-slate-500">{t("settings.subtitle")}</p><section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div className="flex flex-wrap items-start gap-4"><div className="rounded-xl bg-blue-50 p-3 text-blue-700"><Settings2 className="h-6 w-6" /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold text-slate-800">{profile?.name || t("settings.notConfigured")}</h2><span className={`rounded-full px-2 py-1 text-[10px] ${connected ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{connected ? t("settings.connected") : t("settings.disconnected")}</span></div><p className="mt-1 text-sm text-slate-500">{profile ? `${protocolLabel(profile.protocol, locale)} · ${t("settings.model", { model: profile.model || t("settings.unspecified") })}` : t("settings.providers")}</p>{profile?.notes && <p className="mt-3 text-xs leading-5 text-slate-500">{profile.notes}</p>}</div>{profile?.website_url && <a href={profile.website_url} target="_blank" rel="noreferrer" className="shrink-0 text-slate-400 hover:text-blue-600"><ExternalLink className="h-4 w-4" /></a>}</div><div className="mt-6 flex flex-wrap gap-3"><button onClick={onOpen} className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white">{profile ? t("settings.edit") : t("settings.addProvider")}</button>{connected && <button onClick={onDisconnect} className="flex items-center gap-1 rounded-lg border border-slate-200 px-4 py-2.5 text-sm text-slate-600"><Power className="h-4 w-4" />{t("settings.disconnect")}</button>}</div></section></div></div>;
}
