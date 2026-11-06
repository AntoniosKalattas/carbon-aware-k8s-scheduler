package main

import (
	"example.com/green-scheduler/internal/plugin"
	"k8s.io/component-base/cli"
	"k8s.io/kubernetes/cmd/kube-scheduler/app"
	"os"
)

func main() {
	command := app.NewSchedulerCommand(app.WithPlugin(plugin.Name, plugin.New))
	os.Exit(cli.Run(command))
}
