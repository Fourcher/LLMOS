/* A GTK 3 module: hides the "you are using the root account" bar that Thunar and Mousepad show.
 *
 * LLM OS runs the owner's programs as root on purpose (one owner, full control), so the bar is noise.
 * Loaded through GTK3_MODULES=/usr/lib/llmos/gtk/noroot-<arch>.so (desk.py _child_env). Nothing else changes:
 * the programs still run as root and keep every other bar (a file changed on disk, and so on).
 *
 * No GTK headers: the few GLib/GTK calls are declared here with plain pointers and resolved at load time from the
 * program that loads the module, so one source builds for every architecture with clang + lld only:
 *   clang --target=aarch64-linux-musl -O2 -fPIC -c noroot.c -o a.o && ld.lld -shared a.o -o noroot-aarch64.so
 *   clang --target=x86_64-linux-musl  -O2 -fPIC -c noroot.c -o x.o && ld.lld -shared x.o -o noroot-x86_64.so
 */
typedef unsigned long GType;
typedef int gboolean;
typedef unsigned int guint;

extern guint g_signal_lookup(const char *name, GType itype);
extern unsigned long g_signal_add_emission_hook(guint signal_id, guint detail, void *hook, void *data, void *destroy);
extern void *g_value_get_object(const void *value);
extern int g_type_check_instance_is_a(void *instance, GType iface_type);
extern guint g_idle_add(void *function, void *data);
extern GType gtk_widget_get_type(void);
extern void *g_type_class_ref(GType type);
extern GType gtk_label_get_type(void);
extern GType gtk_info_bar_get_type(void);
extern const char *gtk_label_get_text(void *label);
extern void *gtk_widget_get_parent(void *widget);
extern void gtk_widget_hide(void *widget);
extern void gtk_widget_set_no_show_all(void *widget, gboolean no_show_all);
extern char *dgettext(const char *domain, const char *msgid);
extern char *strstr(const char *haystack, const char *needle);
extern int strcmp(const char *a, const char *b);

static const char *MSG = "Warning: you are using the root account. You may harm your system.";

static int is_root_warning(const char *text)
{
    if (!text)
        return 0;
    if (strstr(text, "root account"))
        return 1;
    /* the same words in the owner's language */
    const char *domains[] = { "thunar", "mousepad", 0 };
    for (int i = 0; domains[i]; i++) {
        const char *t = dgettext(domains[i], MSG);
        if (t && t != MSG && strcmp(t, MSG) != 0 && strcmp(text, t) == 0)
            return 1;
    }
    return 0;
}

static gboolean hide_later(void *bar)
{
    gtk_widget_set_no_show_all(bar, 1);
    gtk_widget_hide(bar);
    return 0;
}

static gboolean on_map(void *hint, guint n, const void *values, void *data)
{
    (void)hint; (void)data;
    if (n < 1)
        return 1;
    void *w = g_value_get_object(values);
    if (!w || !g_type_check_instance_is_a(w, gtk_label_get_type()))
        return 1;
    if (!is_root_warning(gtk_label_get_text(w)))
        return 1;
    void *bar = w;
    for (void *p = gtk_widget_get_parent(w); p; p = gtk_widget_get_parent(p)) {
        if (g_type_check_instance_is_a(p, gtk_info_bar_get_type())) {
            bar = p;
            break;
        }
    }
    g_idle_add((void *)hide_later, bar);
    return 1;   /* keep the hook */
}

void gtk_module_init(int *argc, char ***argv)
{
    (void)argc; (void)argv;
    g_type_class_ref(gtk_widget_get_type());          /* "map" exists once the widget class is set up */
    g_signal_add_emission_hook(g_signal_lookup("map", gtk_widget_get_type()), 0, (void *)on_map, 0, 0);
}
