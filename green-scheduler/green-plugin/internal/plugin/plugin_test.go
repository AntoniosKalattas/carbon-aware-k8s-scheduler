package plugin

import (
	"context"
	"k8s.io/apimachinery/pkg/runtime"
	"testing"
)

func TestFactory(t *testing.T) {
	p, err := New(context.Background(), &runtime.Unknown{Raw: []byte(`{"mode":"energy","seconds":10.5,"regions":{"cyprus":{"watts":40,"carbon":700}}}`)}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if p.Name() != Name {
		t.Fatal("wrong plugin name")
	}
	if _, err := New(context.Background(), nil, nil); err == nil {
		t.Fatal("missing config accepted")
	}
	if _, err := New(context.Background(), &runtime.Unknown{Raw: []byte(`{"mode":`)}, nil); err == nil {
		t.Fatal("malformed config accepted")
	}
}
