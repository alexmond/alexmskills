// A Go producer. No module to import: it calls the CLI.
//
//	PROGRESS_CLI="python3 <plugin>/scripts/progress.py" go run .
//	go run .                        # no PROGRESS_CLI: runs untracked
//
// The same three calls work from any language that can start a process:
// start prints a token, step advances it, finish closes it.
package main

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// progress never returns an error: a missing or broken tracker must not fail
// the job it watches.
func progress(args ...string) string {
	cli := strings.Fields(os.Getenv("PROGRESS_CLI"))
	if len(cli) == 0 {
		return ""
	}
	if len(args) > 0 && args[0] == "start" {
		// Liveness is tied to THIS process, not the short-lived CLI call.
		args = append(args, "--pid", strconv.Itoa(os.Getpid()))
	}
	out, err := exec.Command(cli[0], append(cli[1:], args...)...).Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func main() {
	delay := 50 * time.Millisecond
	if s, err := strconv.ParseFloat(os.Getenv("DELAY"), 64); err == nil {
		delay = time.Duration(s * float64(time.Second))
	}

	shards := 24
	token := progress("start", "--name", "go reindex", "--total", strconv.Itoa(shards))
	// A deferred finish reports a panic as a failure instead of leaving the
	// row for the orphan sweep.
	defer func() {
		if token == "" {
			return
		}
		if r := recover(); r != nil {
			progress("finish", token, "--fail", fmt.Sprint(r))
			panic(r)
		}
		progress("finish", token)
	}()

	const batch = 4
	for i := 1; i <= shards; i++ {
		time.Sleep(delay) // ← the real work goes here
		if i%batch == 0 && token != "" {
			progress("step", token, "-n", strconv.Itoa(batch), "--detail", fmt.Sprintf("shard %d", i))
		}
	}
	fmt.Printf("reindexed %d shards\n", shards)
}
