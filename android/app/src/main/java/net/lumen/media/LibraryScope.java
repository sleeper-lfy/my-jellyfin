package net.lumen.media;

/** Zero represents all libraries in existing intents and queue preferences. */
final class LibraryScope {
    static final long BUILTIN = -1;
    private static final String BUILTIN_VALUE = "builtin";

    static Object value(long scope) {
        return scope == BUILTIN ? BUILTIN_VALUE : scope;
    }

    static long read(org.json.JSONObject filters) {
        if (filters == null) return 0;
        return BUILTIN_VALUE.equals(filters.optString("media_library_id"))
                ? BUILTIN : filters.optLong("media_library_id", 0);
    }

    static String query(long scope, String separator) {
        return scope == 0 ? "" : separator + "media_library_id=" + value(scope);
    }
}
