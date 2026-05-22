/**
 * Glossary slice (081): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "081" as const;
export const termEn = "yield curve" as const;
export function describeTerm(): string {
  return termEn;
}
