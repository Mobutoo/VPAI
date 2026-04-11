#!/usr/bin/env bats

setup() {
  TMPDIR_ROOT="$(mktemp -d)"
  export MOP_DATA_DIR="$TMPDIR_ROOT/mop"
  mkdir -p "$MOP_DATA_DIR/index"
  printf '\xef\xbb\xbfid;title;keywords;severity;perimeter;filename;sub_procs;created_at\n' > "$MOP_DATA_DIR/index/mops-index.csv"
  SCRIPT="$BATS_TEST_DIRNAME/alloc-and-append.sh"
}

teardown() {
  rm -rf "$TMPDIR_ROOT"
}

@test "allocate returns first ID as MOP-YYYY-0001" {
  local year
  year=$(date +%Y)
  run "$SCRIPT" allocate '{"title":"test","keywords":["a"],"severity":"minor","perimeter":"test"}'
  [ "$status" -eq 0 ]
  [[ "$output" == "MOP-${year}-0001" ]]
}

@test "allocate increments sequentially" {
  "$SCRIPT" allocate '{"title":"t1","keywords":["a"],"severity":"minor","perimeter":"p"}'
  "$SCRIPT" confirm MOP-$(date +%Y)-0001 '{"title":"t1","keywords":["a"],"severity":"minor","perimeter":"p","filename":"t1.pdf","sub_procs":""}'
  run "$SCRIPT" allocate '{"title":"t2","keywords":["b"],"severity":"minor","perimeter":"p"}'
  [ "$status" -eq 0 ]
  [[ "$output" == "MOP-$(date +%Y)-0002" ]]
}

@test "confirm appends CSV line" {
  "$SCRIPT" allocate '{"title":"t","keywords":["a"],"severity":"minor","perimeter":"p"}'
  run "$SCRIPT" confirm MOP-$(date +%Y)-0001 '{"title":"t","keywords":["a"],"severity":"minor","perimeter":"p","filename":"t.pdf","sub_procs":"SP-01"}'
  [ "$status" -eq 0 ]
  run wc -l "$MOP_DATA_DIR/index/mops-index.csv"
  [[ "$output" =~ ^2\  ]]
}

@test "rollback removes pending without CSV change" {
  "$SCRIPT" allocate '{"title":"t","keywords":["a"],"severity":"minor","perimeter":"p"}'
  run "$SCRIPT" rollback MOP-$(date +%Y)-0001
  [ "$status" -eq 0 ]
  run wc -l "$MOP_DATA_DIR/index/mops-index.csv"
  [[ "$output" =~ ^1\  ]]
}

@test "10 parallel allocates produce 10 distinct IDs" {
  for i in {1..10}; do
    ( "$SCRIPT" allocate "{\"title\":\"t$i\",\"keywords\":[\"x\"],\"severity\":\"minor\",\"perimeter\":\"p\"}" ) &
  done
  wait
  # Count .pending files
  local count
  count=$(ls "$MOP_DATA_DIR/index/.pending/" 2>/dev/null | wc -l)
  [ "$count" -eq 10 ]
}

@test "malformed JSON fails with non-zero exit" {
  run "$SCRIPT" allocate 'not json'
  [ "$status" -ne 0 ]
}
