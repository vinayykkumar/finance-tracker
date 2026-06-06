/**
 * Glossary slice (077): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "077" as const;
export const termEn = "variable expense" as const;
export function describeTerm(): string {
  return termEn;
}
