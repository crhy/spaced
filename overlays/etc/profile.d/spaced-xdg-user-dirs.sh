# Create standard XDG user directories on first login if they do not exist.
for dir in Desktop Documents Downloads Music Pictures Videos; do
  target="$HOME/$dir"
  if [ ! -d "$target" ]; then
    mkdir -p "$target"
  fi
done
