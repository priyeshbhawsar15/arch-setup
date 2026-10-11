-- Personal startup applications.
-- A watchdog restart can leave the shell disconnected. Config reload normally
-- doesn't rerun startup; recover only when shell IPC is unavailable.
hl.on("config.reloaded", function()
  hl.exec_cmd("~/.config/hypr/scripts/shell-recover.sh")
end)
