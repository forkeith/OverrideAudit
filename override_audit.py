import sublime
import sublime_plugin

import os

from .lib.packages import PackageInfo, PackageList, PackageFileSet
from .lib.output_view import output_to_view

###-----------------------------------------------------------------------------

def packages_with_overrides(pkg_list, name_list=None):
    """
    Collect a list of package names from the given package list for which there
    is at least a single (simple) override file and which is not in the list of
    packages to ignore overrides in.

    Optionally, if name_list is provided, the list of package names will be
    filtered to only include packages whose name also exists in the name list.
    """
    settings = sublime.load_settings("OverrideAudit.sublime-settings")
    ignored = settings.get("ignore_overrides_in", [])

    items = [name for name, pkg in pkg_list if len(pkg.override_files()) > 0
                                               and name not in ignored]

    if name_list is not None:
        items = list(filter(lambda name: name in name_list, items))

    return items

def decorate_package_name(pkg_info, status=False):
    """
    Decorate the name of the provided package with a prefix that describes its
    status and optionally also a suffix if it is a complete override.
    """
    suffix = ""
    if status and pkg_info.has_possible_overrides(simple=False):
        suffix = " <Complete Override>"

    return "[{}{}{}] {}{}".format(
               "S" if pkg_info.shipped_path is not None else " ",
               "I" if pkg_info.installed_path is not None else " ",
               "U" if pkg_info.unpacked_path is not None else " ",
               pkg_info.name,
               suffix)

###-----------------------------------------------------------------------------

class OverrideAuditDiffPackage(sublime_plugin.WindowCommand):
    def _perform_diff(self, pkg_info, context_lines, result):
        for file in pkg_info.override_files():
            result.append("    {}".format(file))

            diff = pkg_info.override_diff(file, context_lines,
                                          empty_result="No differences found",
                                          indent=8)
            if diff is None:
                diff = "Error diffing override; please check the console"
            result.extend([diff, ""])

        result.append("")


    def _diff_packages(self, names, pkg_list, single_package):
        settings = sublime.load_settings("OverrideAudit.sublime-settings")
        context_lines = settings.get("diff_context_lines", 3)

        result = []
        title = "Override Diff Report: "
        if len(names) == 1 and single_package:
            title += names[0]
            result.append("Diffing overrides for {}\n".format(names[0]))
        else:
            title += "All Packages"
            result.append("Diffing overrides for {} packages\n".format(
                          len(names)))

        for name in names:
            pkg_info = pkg_list[name]
            result.append (decorate_package_name(pkg_info, status=True))

            self._perform_diff(pkg_info, context_lines, result)

        output_to_view(self.window,
                       title,
                       result,
                       reuse=settings.get("reuse_views", True),
                       clear=settings.get("clear_existing", True),
                       syntax="Packages/OverrideAudit/syntax/OverrideAudit-diff.sublime-syntax")

    def run(self, package=None):
        pkg_list = PackageList()

        settings = sublime.load_settings("OverrideAudit.sublime-settings")
        ignored = settings.get("ignore_overrides_in", [])

        name_list = None if package is None else [package]
        items = packages_with_overrides(pkg_list, name_list)

        self._diff_packages(items, pkg_list, package is not None)

###-----------------------------------------------------------------------------

class OverrideAuditDiffOverrideCommand(sublime_plugin.WindowCommand):
    def _perform_diff(self, pkg_info, file):
        settings = sublime.load_settings("OverrideAudit.sublime-settings")
        action = settings.get("diff_unchanged", "diff")

        diff_info = pkg_info.override_diff(file, settings.get("diff_context_lines", 3))

        if diff_info is None:
            return

        if diff_info == "":
            sublime.status_message("No changes detected in override")

            if action == "open":
                full_filename = os.path.join(sublime.packages_path(), pkg_info.name, file)
                self.window.open_file(full_filename)
                return
            elif action == "ignore":
                return

        output_to_view(self.window,
                       "Override of %s" % os.path.join(pkg_info.name, file),
                       "No differences found" if diff_info == "" else diff_info,
                       reuse=settings.get("reuse_views", True),
                       clear=settings.get("clear_existing", True),
                       syntax="Packages/Diff/Diff.sublime-syntax")

    def _file_pick(self, pkg_info, override_list, index):
        if index >= 0:
            self._perform_diff(pkg_info, override_list[index])

    def _show_override_list(self, pkg_info):
        override_list = list(pkg_info.override_files())
        if not override_list:
            print("Package '%s' has no overrides" % pkg_info.name)
        self.window.show_quick_panel(
            items=override_list,
            on_select=lambda i: self._file_pick(pkg_info, override_list, i))

    def _pkg_pick(self, pkg_list, pkg_override_list, index, bulk):
        if index >= 0:
            pkg_info = pkg_list[pkg_override_list[index]]
            if not bulk:
                self._show_override_list(pkg_info)
            else:
                self.window.run_command("override_audit_diff_package",
                                        {"package": pkg_info.name})

    def _show_pkg_list(self, pkg_list, bulk):
        items = packages_with_overrides(pkg_list)

        if not items:
            print("No unignored packages have overrides")
        self.window.show_quick_panel(
                items=items,
                on_select=lambda i: self._pkg_pick(pkg_list, items, i, bulk))

    def run(self, package=None, file=None, bulk=False):
        pkg_list = PackageList()

        if package is None:
            self._show_pkg_list(pkg_list, bulk)
        else:
            if package in pkg_list:
                pkg_info = pkg_list[package]
                if file is None:
                    self._show_override_list(pkg_info)
                else:
                    if pkg_info.has_possible_overrides():
                        self._perform_diff(pkg_info, file)
                    else:
                        print("Package '%s' has no overrides to diff" % package)
            else:
                print("Unable to diff; no such package '%s'" % package)

###-----------------------------------------------------------------------------

class OverrideAuditPackageReportCommand(sublime_plugin.WindowCommand):
    def run(self):
        pkg_list = PackageList()
        pkg_counts = pkg_list.package_counts()

        settings = sublime.load_settings("OverrideAudit.sublime-settings")

        title = "{} Total Packages".format(len(pkg_list))
        t_sep = "=" * len(title)

        fmt = '{{:>{}}}'.format(len(str(max(pkg_counts))))
        stats = ("{0} [S]hipped with Sublime\n"
                 "{0} [I]nstalled (user) sublime-package files\n"
                 "{0} [U]npacked in Packages\\ directory\n"
                 "{0} Currently in ignored_packages\n"
                 "{0} Installed dependencies\n").format(fmt).format(*pkg_counts)

        row = "| {:<40} | {:3} | {:3} | {:<3} |".format("", "", "", "")
        r_sep = "-" * len(row)

        result = [title, t_sep, "", stats, r_sep]
        for pkg_name, pkg_info in pkg_list:
            if pkg_info.is_disabled:
                pkg_name = "[{}]".format (pkg_name)
            elif pkg_info.is_dependency:
                pkg_name = "<{}>".format (pkg_name)
            result.append (
                "| {:<40} | [{:1}] | [{:1}] | [{:1}] |".format(
                pkg_name,
                "S" if pkg_info.shipped_path is not None else " ",
                "I" if pkg_info.installed_path is not None else " ",
                "U" if pkg_info.unpacked_path is not None else " "))
        result.extend([r_sep, ""])

        output_to_view(self.window,
                       "OverrideAudit: Package Report",
                       result,
                       reuse=settings.get("reuse_views", True),
                       clear=settings.get("clear_existing", True),
                       syntax="Packages/OverrideAudit/syntax/OverrideAudit-pkgList.sublime-syntax")

###-----------------------------------------------------------------------------

class OverrideAuditOverrideReport(sublime_plugin.WindowCommand):
    def run(self):
        pkg_list = PackageList()
        pkg_counts = pkg_list.package_counts()

        settings = sublime.load_settings("OverrideAudit.sublime-settings")
        ignored = settings.get ("ignore_overrides_in", [])

        result = []
        for pkg_name, pkg_info in pkg_list:
            normal_overrides = pkg_info.override_files(simple=True)
            shipped_override = pkg_info.has_possible_overrides(simple=False)
            if pkg_name in ignored or (not normal_overrides and not shipped_override):
               continue

            result.append (decorate_package_name(pkg_info, status=True))

            if normal_overrides:
                result.extend(["  `- {}".format(item) for item in normal_overrides])
            else:
                result.append ("    [No simple overrides found]")
            result.append("")

        if len(result) == 0:
            result.append("No packages with overrides found")

        output_to_view(self.window,
                       "OverrideAudit: Override Report",
                       result,
                       reuse=settings.get("reuse_views", True),
                       clear=settings.get("clear_existing", True),
                       syntax="Packages/OverrideAudit/syntax/OverrideAudit-overrideList.sublime-syntax")
