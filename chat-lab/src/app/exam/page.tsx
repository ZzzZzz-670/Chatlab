import SubPagePlaceholder from "@/components/SubPagePlaceholder";

export default function ExamPage() {
  return (
    <SubPagePlaceholder
      title="一键分析试卷"
      subtitle="从错题和卷面表现里找到真实卡点"
      items={["试卷上传", "错因归类", "提升建议"]}
    />
  );
}
