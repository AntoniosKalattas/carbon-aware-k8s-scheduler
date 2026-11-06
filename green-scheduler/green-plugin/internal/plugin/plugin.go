package plugin

import (
	"context"
	"example.com/green-scheduler/internal/model"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/klog/v2"
	fwk "k8s.io/kube-scheduler/framework"
	frameworkruntime "k8s.io/kubernetes/pkg/scheduler/framework/runtime"
)

const Name = "GreenScore"

type GreenScore struct{ config model.Config }

var _ fwk.ScorePlugin = &GreenScore{}

func (g *GreenScore) Name() string                         { return Name }
func (g *GreenScore) ScoreExtensions() fwk.ScoreExtensions { return nil }
func New(_ context.Context, args runtime.Object, _ fwk.Handle) (fwk.Plugin, error) {
	var c model.Config
	if err := frameworkruntime.DecodeInto(args, &c); err != nil {
		return nil, err
	}
	if err := c.Validate(); err != nil {
		return nil, err
	}
	return &GreenScore{config: c}, nil
}
func (g *GreenScore) Score(ctx context.Context, _ fwk.CycleState, pod *v1.Pod, node fwk.NodeInfo) (int64, *fwk.Status) {
	region := node.Node().Labels["region"]
	score := g.config.Score(region)
	klog.FromContext(ctx).V(4).Info("GreenScore decision", "pod", klog.KObj(pod), "node", node.Node().Name, "region", region, "mode", g.config.Mode, "score", score)
	return score, nil
}
