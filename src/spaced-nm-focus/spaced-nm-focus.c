/*
 * GTK 3 module that puts the cursor in the password field of nm-applet's
 * Wi-Fi dialogs (issue #234).
 *
 * libnma 1.10 disabled the code that focused the security method's default
 * field (the "#if 0" block in nma-wifi-dialog.c), so a new network's dialog
 * focuses the device combo and a saved network's dialog focuses nothing.
 * /etc/X11/Xsession.d/52spaced-nm-focus adds this module to GTK_MODULES; it
 * does nothing in any program other than nm-applet.
 */
#include <gtk/gtk.h>

static gboolean
is_password_entry (GtkWidget *widget)
{
    return GTK_IS_ENTRY (widget)
        && !gtk_entry_get_visibility (GTK_ENTRY (widget))
        && gtk_widget_get_sensitive (widget);
}

static gboolean
focus_password_on_map (GSignalInvocationHint *hint, guint n_params,
                       const GValue *params, gpointer data)
{
    GtkWidget *widget = g_value_get_object (&params[0]);
    GtkWidget *toplevel, *focus;

    if (!is_password_entry (widget))
        return TRUE;
    toplevel = gtk_widget_get_toplevel (widget);
    if (!GTK_IS_DIALOG (toplevel))
        return TRUE;

    /* Leave the cursor where the user must type first: an earlier password
     * field, or an empty name field such as a hidden network's SSID. */
    focus = gtk_window_get_focus (GTK_WINDOW (toplevel));
    if (focus && GTK_IS_ENTRY (focus)
        && (is_password_entry (focus)
            || gtk_entry_get_text_length (GTK_ENTRY (focus)) == 0))
        return TRUE;

    gtk_widget_grab_focus (widget);
    return TRUE;
}

G_MODULE_EXPORT void
gtk_module_init (gint *argc, gchar ***argv)
{
    if (g_strcmp0 (g_get_prgname (), "nm-applet") != 0)
        return;
    /* Modules load before any widget exists, so the class (and its "map"
     * signal) must be created first. The reference is kept for good. */
    g_type_class_ref (GTK_TYPE_ENTRY);
    g_signal_add_emission_hook (g_signal_lookup ("map", GTK_TYPE_WIDGET), 0,
                                focus_password_on_map, NULL, NULL);
}
