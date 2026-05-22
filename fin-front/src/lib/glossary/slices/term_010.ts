/**
 * Glossary slice (010): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "010" as const;
export const termEn = "bond yield" as const;
export function describeTerm(): string {
  return termEn;
}
