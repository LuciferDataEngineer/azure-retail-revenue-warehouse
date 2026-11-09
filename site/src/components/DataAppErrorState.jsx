import React, { Component } from "react";
import { DataErrorState } from "@openai/data-ui/primitives/DataErrorState.jsx";

export function DataAppErrorState(props) {
  return <DataErrorState {...props} height={420} tag="main" />;
}

export class DataAppErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    return this.state.error
      ? <DataAppErrorState error={this.state.error} surface={this.props.surface} />
      : this.props.children;
  }
}
