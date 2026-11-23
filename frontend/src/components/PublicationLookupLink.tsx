import { useI18n } from "../i18n";

const PUBLICATION_NUMBER = /^([a-z]{2})[ -]?([0-9]{3,16})[ -]?([a-z][0-9]?)$/i;

export function PublicationLookupLink({ publicationNumber }: { publicationNumber: unknown }) {
  const { t } = useI18n();
  if (typeof publicationNumber !== "string") return null;

  const match = PUBLICATION_NUMBER.exec(publicationNumber.trim());
  if (!match) return null;

  const [, office, digits, kind] = match;
  const number = (office + digits + kind).toUpperCase();
  return (
    <a
      href={`https://patents.google.com/patent/${number}`}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={t("visual.openGooglePatents", { number })}
      className="w-fit text-xs text-blue-700 underline underline-offset-2 hover:text-blue-900"
    >
      Google Patents <span aria-hidden="true">↗</span>
    </a>
  );
}
